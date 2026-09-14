import json
import re
import time

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import AgentLog, Document, User
from ..schemas import (
    SearchResponse, SearchHit, ChatRequest, ChatResponse, ChatSource,
    AgentRequest, AgentResponse, CancelRequest,
)
from ..security import get_api_or_user, get_current_user
from ..services import search as search_svc
from ..services import access, llm, agent, cancel

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("", response_model=SearchResponse)
def search_documents(
    q: str = Query(..., min_length=1, description="Поисковый запрос"),
    mode: str = Query("hybrid", pattern="^(hybrid|semantic|keyword)$"),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    user: User = Depends(get_api_or_user),
):
    """Поиск по смыслу, словоформам и реквизитам. Поддерживает логические
    операторы И / ИЛИ / НЕ и фразу в кавычках (ТЗ АГП п. 8, 12.2)."""
    hits = search_svc.search(q, mode=mode, size=size,
                             allowed_types=access.allowed_type_values(db, user))
    return SearchResponse(
        query=q,
        mode=mode,
        total=len(hits),
        hits=[SearchHit(**h) for h in hits],
    )


@router.post("/chat", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """RAG: retrieve the most relevant documents, then let the local LLM answer
    grounded in their text, citing sources."""
    hits = search_svc.search(payload.question, mode="hybrid", size=settings.RAG_TOP_K,
                             allowed_types=access.allowed_type_values(db, user),
                             operators=False)

    contexts, sources = [], []
    for h in hits:
        doc = db.get(Document, h["id"])
        if not doc:
            continue
        text = (h.get("chunk_text") or doc.ocr_text or doc.description or "").strip()
        text = text[: settings.RAG_CONTEXT_CHARS]
        if text:
            contexts.append({"title": doc.title, "text": text})
        fragments = h.get("fragments") or []
        sources.append(
            ChatSource(
                id=doc.id, title=doc.title, fond=doc.fond,
                opis=doc.opis, delo=doc.delo, score=h["score"],
                page_no=fragments[0]["page_no"] if fragments else None,
                fragment=agent.quote(fragments[0]["text"]) if fragments else "",
            )
        )

    if not contexts:
        return ChatResponse(
            answer="В архиве не найдено документов, относящихся к вашему вопросу.",
            sources=[],
        )

    if not llm.is_ready():
        return ChatResponse(
            answer="Модель ИИ ещё загружается (первый запуск, ~несколько минут). "
            "Пока показаны найденные документы — повторите вопрос чуть позже.",
            sources=sources,
            model_ready=False,
        )

    try:
        text = llm.answer(payload.question, contexts)
    except Exception as exc:  # noqa: BLE001
        return ChatResponse(
            answer=f"Не удалось получить ответ от модели: {exc}",
            sources=sources,
            model_ready=False,
        )

    text, sources = _postprocess(text, sources)
    return ChatResponse(answer=text, sources=sources)


def _journal(db: Session, user: User, question: str, result: dict,
             route: str, started: float, cancelled: bool = False) -> None:
    """Журнал запросов и ответов ИИ-агента (ТЗ АГП п. 12.6).

    Пишется для каждого ответа, включая отказы и остановленную генерацию:
    ценность журнала как раз в том, чтобы видеть, когда ассистент отвечать
    отказался. Сбой записи не должен лишать пользователя ответа.
    """
    answer = result.get("answer", "")
    try:
        db.add(AgentLog(
            user_email=user.email,
            question=question[:4000],
            answer=answer[:8000],
            sources=json.dumps([{"id": s.get("id"), "title": s.get("title"),
                                 "page_no": s.get("page_no")}
                                for s in result.get("sources", [])],
                               ensure_ascii=False),
            confidence=result.get("confidence") or "",
            route=route,
            refused=_REFUSAL in answer.lower(),
            cancelled=cancelled,
            duration_ms=int((time.monotonic() - started) * 1000),
        ))
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()


@router.post("/agent", response_model=AgentResponse)
def agent_chat(
    payload: AgentRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Conversational AI agent. Given the full dialog history, the agent decides
    when to search the archive and read documents, then answers grounded in them."""
    history = [{"role": m.role, "content": m.content} for m in payload.messages]
    question = next((m["content"] for m in reversed(history)
                     if m.get("role") == "user"), "")
    started = time.monotonic()
    allowed = access.allowed_types(db, user)
    allowed_values = None if allowed is None else sorted(t.value for t in allowed)

    # Fast path: generic overview questions are answered instantly from the DB,
    # without loading or invoking the LLM.
    quick = agent.quick_answer(history, db, allowed)
    if quick is not None:
        _journal(db, user, question, quick, "quick", started)
        return AgentResponse(**quick)

    if not llm.is_ready():
        return AgentResponse(
            answer="Модель ИИ ещё загружается (первый запуск, ~несколько минут). "
            "Повторите вопрос чуть позже.",
            sources=[], steps=[], model_ready=False,
        )
    try:
        result = agent.run(history, db, request_id=payload.request_id,
                           allowed=allowed_values)
    except cancel.Cancelled:
        # Пользователь нажал «Стоп»: это штатное завершение, а не сбой.
        stopped = {"answer": "⏹ Генерация остановлена.", "sources": [], "steps": []}
        _journal(db, user, question, stopped, "llm", started, cancelled=True)
        return AgentResponse(**stopped, model_ready=True, cancelled=True)
    except Exception as exc:  # noqa: BLE001
        return AgentResponse(
            answer=f"Ошибка агента: {exc}", sources=[], steps=[], model_ready=True,
        )
    finally:
        cancel.release(payload.request_id)
    _journal(db, user, question, result, "llm", started)
    return AgentResponse(**result)


@router.post("/agent/cancel", status_code=204)
def cancel_agent(payload: CancelRequest, _: User = Depends(get_current_user)):
    """Останавливает генерацию ответа по идентификатору запроса.

    Отдельный эндпоинт, а не разрыв соединения: HTTP-запрос обрабатывается в
    отдельном потоке, и обрыв соединения клиентом сам по себе не прекращает уже
    идущую генерацию на модели. Отметка в реестре доводит отмену до неё."""
    cancel.cancel(payload.request_id)


_REFUSAL = "нет информации по этому вопросу"


def _postprocess(text: str, sources: list[ChatSource]) -> tuple[str, list[ChatSource]]:
    """Show only the sources the answer actually cites, and drop sources entirely
    on a refusal (retrieval always returns top-k, but low-relevance docs must not
    look like they backed the answer)."""
    if _REFUSAL in text.lower():
        return "В архиве нет информации по этому вопросу.", []
    cited = {int(n) for n in re.findall(r"\[(\d+)\]", text)}
    if cited:
        sources = [s for i, s in enumerate(sources, 1) if i in cited]
    return text, sources
