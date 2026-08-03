"""Local LLM via Ollama for RAG answers. Uses stdlib http only (no extra deps).

Data never leaves the perimeter — the model runs in the `ollama` container.
"""
import json
import logging
import urllib.request

from ..config import settings

log = logging.getLogger("llm")

BASE = f"http://{settings.OLLAMA_HOST}:{settings.OLLAMA_PORT}"

SYSTEM_PROMPT = (
    "Ты — ассистент электронного архива Республики Казахстан.\n"
    "СТРОГИЕ ПРАВИЛА:\n"
    "1. Отвечай ИСКЛЮЧИТЕЛЬНО на основе текста приведённых документов.\n"
    "2. НИКОГДА не используй свои общие знания о мире. Ты не знаешь ничего, "
    "кроме этих документов.\n"
    "3. Если в документах нет ответа на вопрос — ответь РОВНО одной фразой: "
    "«В архиве нет информации по этому вопросу.» и больше ничего не добавляй.\n"
    "4. Когда отвечаешь по документам — ссылайся на источники в квадратных "
    "скобках, например [1], [2].\n"
    "5. Отвечай кратко и на языке вопроса (русский или казахский)."
)


def _post(path: str, body: dict, timeout: int) -> dict:
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def is_ready() -> bool:
    """True once the configured model is pulled and available."""
    try:
        req = urllib.request.Request(BASE + "/api/tags")
        with urllib.request.urlopen(req, timeout=5) as resp:
            tags = json.loads(resp.read().decode("utf-8"))
    except Exception:  # noqa: BLE001
        return False
    want = settings.OLLAMA_MODEL
    # Ollama reports "qwen2.5:7b"; treat a bare "qwen2.5" as "qwen2.5:latest".
    want_full = want if ":" in want else f"{want}:latest"
    names = {m.get("name", "") for m in tags.get("models", [])}
    return want in names or want_full in names


def ensure_model() -> None:
    """Pull the model if missing (best-effort, may take minutes on first run)."""
    if is_ready():
        return
    log.info("Pulling Ollama model %s …", settings.OLLAMA_MODEL)
    _post("/api/pull", {"name": settings.OLLAMA_MODEL, "stream": False}, timeout=3600)
    log.info("Ollama model %s ready", settings.OLLAMA_MODEL)


ANSWER_SYSTEM = (
    "Ты — ассистент электронного архива Республики Казахстан. Внимательно прочитай "
    "приведённые документы и ответь на вопрос пользователя, опираясь на их "
    "содержимое.\n"
    "• Если ответ есть в документах — дай его чётко и укажи источник в квадратных "
    "скобках, например [1].\n"
    "• Отвечай только по документам, не добавляй факты из общих знаний.\n"
    "• Напиши «В архиве нет информации по этому вопросу.» ТОЛЬКО если в документах "
    "действительно нет нужных данных. Не отказывайся, если данные есть.\n"
    "• Отвечай кратко и на языке вопроса."
)


def chat(messages: list[dict], tools: list[dict] | None = None, timeout: int = 300) -> dict:
    """Low-level chat call. Returns the assistant `message` dict, which may contain
    `tool_calls`. Used by the agent loop."""
    body = {
        "model": settings.OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0, "num_ctx": 8192},
    }
    if tools:
        body["tools"] = tools
    return _post("/api/chat", body, timeout).get("message", {})


_ANNOTATE_SYSTEM = (
    "Ты — опытный архивариус. Составляешь краткую аннотацию документа для архивной "
    "описи: только по существу содержания, без вводных фраз и оценок."
)


def annotate(title: str, text: str, doc_type: str = "") -> str:
    """Generate a 2–3 sentence archival annotation (опись) of the document."""
    text = (text or "").strip()
    if not text:
        return ""
    prompt = (
        f"Тип документа: {doc_type or 'не указан'}.\nЗаголовок: {title}.\n\n"
        f"Текст документа:\n{text[:3000]}\n\n"
        "Составь аннотацию для архивной описи (2–3 предложения): о чём документ, "
        "ключевые стороны, предмет, суммы, даты и номера, если они есть. "
        "Пиши по-русски, только аннотацию."
    )
    resp = _post(
        "/api/generate",
        {"model": settings.OLLAMA_MODEL, "system": _ANNOTATE_SYSTEM, "prompt": prompt,
         "stream": False, "options": {"temperature": 0.2, "num_ctx": 8192, "num_predict": 220}},
        timeout=600,
    )
    return resp.get("response", "").strip()


def classify(title: str, text: str, types: list[str]) -> str:
    """Return the model's best-guess document type label from the given list."""
    text = (text or "").strip()
    if not text:
        return ""
    prompt = (
        f"Заголовок: {title}\n\nТекст:\n{text[:1500]}\n\n"
        f"Определи тип документа СТРОГО из списка: {', '.join(types)}.\n"
        "Ответь только точным названием типа из списка, без пояснений."
    )
    resp = _post(
        "/api/generate",
        {"model": settings.OLLAMA_MODEL, "prompt": prompt, "stream": False,
         "options": {"temperature": 0, "num_ctx": 4096, "num_predict": 20}},
        timeout=300,
    )
    return resp.get("response", "").strip()


def answer(question: str, contexts: list[dict]) -> str:
    """contexts: [{'title': str, 'text': str}]. Returns a grounded answer."""
    blocks = "\n\n".join(
        f"[{i + 1}] {c['title']}\n{c['text']}" for i, c in enumerate(contexts)
    )
    prompt = (
        f"Документы из архива:\n{blocks}\n\n"
        f"Вопрос: {question}\n\n"
        f"Ответ (со ссылками на источники):"
    )
    resp = _post(
        "/api/generate",
        {
            "model": settings.OLLAMA_MODEL,
            "system": ANSWER_SYSTEM,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0, "num_ctx": 8192},
        },
        timeout=300,
    )
    return resp.get("response", "").strip()
