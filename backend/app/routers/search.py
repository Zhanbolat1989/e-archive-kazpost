import re

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import User, Document
from ..schemas import (
    SearchResponse, SearchHit, ChatRequest, ChatResponse, ChatSource,
    AgentRequest, AgentResponse,
)
from ..security import get_current_user
from ..services import search as search_svc
from ..services import llm, agent

router = APIRouter(prefix="/api/search", tags=["search"])


@router.get("", response_model=SearchResponse)
def search_documents(
    q: str = Query(..., min_length=1, description="Поисковый запрос"),
    mode: str = Query("hybrid", pattern="^(hybrid|semantic|keyword)$"),
    size: int = Query(20, ge=1, le=100),
    _: User = Depends(get_current_user),
):
    hits = search_svc.search(q, mode=mode, size=size)
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
    _: User = Depends(get_current_user),
):
    """RAG: retrieve the most relevant documents, then let the local LLM answer
    grounded in their text, citing sources."""
    hits = search_svc.search(payload.question, mode="hybrid", size=settings.RAG_TOP_K)

    contexts, sources = [], []
    for h in hits:
        doc = db.get(Document, h["id"])
        if not doc:
            continue
        text = (doc.ocr_text or doc.description or "").strip()[: settings.RAG_CONTEXT_CHARS]
        if text:
            contexts.append({"title": doc.title, "text": text})
        sources.append(
            ChatSource(
                id=doc.id, title=doc.title, fond=doc.fond,
                opis=doc.opis, delo=doc.delo, score=h["score"],
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


@router.post("/agent", response_model=AgentResponse)
def agent_chat(
    payload: AgentRequest,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Conversational AI agent. Given the full dialog history, the agent decides
    when to search the archive and read documents, then answers grounded in them."""
    history = [{"role": m.role, "content": m.content} for m in payload.messages]

    # Fast path: generic overview questions are answered instantly from the DB,
    # without loading or invoking the LLM.
    quick = agent.quick_answer(history, db)
    if quick is not None:
        return AgentResponse(**quick)

    if not llm.is_ready():
        return AgentResponse(
            answer="Модель ИИ ещё загружается (первый запуск, ~несколько минут). "
            "Повторите вопрос чуть позже.",
            sources=[], steps=[], model_ready=False,
        )
    try:
        result = agent.run(history, db)
    except Exception as exc:  # noqa: BLE001
        return AgentResponse(
            answer=f"Ошибка агента: {exc}", sources=[], steps=[], model_ready=True,
        )
    return AgentResponse(**result)


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
