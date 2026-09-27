import { useState, useRef, useEffect } from "react";
import { api } from "../api.js";
import DocumentModal from "../components/DocumentModal.jsx";

const WELCOME = {
  role: "assistant",
  content:
    "Здравствуйте! Я ИИ-агент архива. Могу искать по документам и читать их " +
    "содержимое, чтобы ответить на ваш вопрос — и помню контекст диалога, так что " +
    "можно задавать уточняющие вопросы.\n\n" +
    "Например: «Какая была арендная плата по договору 2019 года?», а потом " +
    "«А на какой срок он заключён?»",
  sources: [],
  steps: [],
};

const SUGGESTIONS = [
  "Покажи все счета-фактуры за 2021 год",
  "Какая арендная плата по договору аренды?",
  "Сколько всего договоров с ТОО «Кагаз Логистик» и на какую сумму?",
  "Какие условия оплаты в договоре подряда?",
];

const STEP_ICON = { search_archive: "🔍", filter_documents: "🗂️", read_document: "📄" };
const STEP_LABEL = {
  search_archive: "Поиск по содержимому",
  filter_documents: "Фильтр по метаданным",
  read_document: "Чтение документа",
};

const STORAGE_KEY = "earchive_agent_chat";

function loadMessages() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY));
    if (Array.isArray(saved) && saved.length) return saved;
  } catch (_) {}
  return [WELCOME];
}

export default function Search() {
  const [messages, setMessages] = useState(loadMessages);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState(null);
  const endRef = useRef();
  // Управление текущим запросом: контроллер обрывает ожидание в браузере,
  // идентификатор — останавливает генерацию на сервере.
  const abortRef = useRef(null);
  const requestIdRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  // Persist the conversation so it survives tab/route switches and reloads.
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(messages));
    } catch (_) {}
  }, [messages]);

  function newDialog() {
    setMessages([WELCOME]);
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch (_) {}
  }

  function stop() {
    // Сначала сообщаем серверу — он прервёт генерацию и освободит модель;
    // затем обрываем ожидание в браузере.
    const id = requestIdRef.current;
    if (id) api.cancelAgent(id).catch(() => {});
    abortRef.current?.abort();
  }

  async function ask(q) {
    const question = (q ?? input).trim();
    if (!question || busy) return;
    setInput("");
    const next = [...messages, { role: "user", content: question }];
    setMessages(next);
    setBusy(true);

    const requestId =
      crypto.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
    const controller = new AbortController();
    requestIdRef.current = requestId;
    abortRef.current = controller;

    try {
      // Send only clean role/content turns (no tool internals) as history.
      const history = next
        .filter((m) => m.role === "user" || m.role === "assistant")
        .map((m) => ({ role: m.role, content: m.content }));
      const res = await api.agent(history, { requestId, signal: controller.signal });
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          content: res.answer,
          sources: res.sources || [],
          steps: res.steps || [],
          confidence: res.confidence || null,
        },
      ]);
    } catch (err) {
      // Остановка по кнопке — не ошибка, а осознанное действие пользователя.
      const stopped = err.name === "AbortError";
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          content: stopped ? "⏹ Генерация остановлена." : `Ошибка: ${err.message}`,
          sources: [],
          steps: [],
        },
      ]);
    } finally {
      abortRef.current = null;
      requestIdRef.current = null;
      setBusy(false);
    }
  }

  async function openSource(id) {
    setSelected(await api.getDocument(id));
  }

  return (
    <div className="page chat-page">
      <header className="page-head">
        <div>
          <h1>🤖 ИИ-агент архива</h1>
          <p className="muted">
            Диалог с памятью · агент сам ищет и читает документы (локальная модель)
          </p>
        </div>
        {messages.length > 1 && (
          <button className="btn small" onClick={newDialog}>
            Новый диалог
          </button>
        )}
      </header>

      <div className="chat-window">
        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            <div className="msg-avatar">{m.role === "user" ? "Вы" : "ИИ"}</div>
            <div className="msg-body">
              {m.steps && m.steps.length > 0 && (
                <details className="agent-steps">
                  <summary>🧠 Действия агента ({m.steps.length})</summary>
                  {m.steps.map((s, j) => (
                    <div key={j} className="step">
                      <span className="step-icon">{STEP_ICON[s.tool] || "⚙️"}</span>
                      <b>{STEP_LABEL[s.tool] || s.tool}</b>
                      {s.input && <span className="step-input">«{s.input}»</span>}
                      {s.summary && <span className="muted"> — {s.summary}</span>}
                    </div>
                  ))}
                </details>
              )}
              <div className="msg-text">{m.content}</div>
              {m.confidence && m.confidence !== "high" && (
                <div className={`confidence ${m.confidence}`}>
                  {m.confidence === "low"
                    ? "Низкая уверенность: числа в ответе расходятся с текстом документов"
                    : "Средняя уверенность: сверьте ключевые данные по источникам"}
                </div>
              )}
              {m.sources && m.sources.length > 0 && (
                <div className="msg-sources">
                  <div className="msg-sources-label">Источники:</div>
                  {/* Ссылка на документ, страницу и фрагмент:
                      цитата рядом с источником позволяет проверить ответ,
                      не открывая документ целиком. */}
                  {m.sources.map((s, j) => (
                    <div key={s.id} className="source-item">
                      <button className="source-chip" onClick={() => openSource(s.id)}>
                        <span className="source-num">[{j + 1}]</span> {s.title}
                        {s.page_no && <span className="source-fond"> · с. {s.page_no}</span>}
                        {s.fond && <span className="source-fond"> · {s.fond}</span>}
                      </button>
                      {s.fragment && (
                        <div className="source-fragment muted">«{s.fragment}»</div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}

        {busy && (
          <div className="msg assistant">
            <div className="msg-avatar">ИИ</div>
            <div className="msg-body">
              <div className="typing"><span></span><span></span><span></span></div>
              <button className="btn small stop-btn" onClick={stop}>
                ⏹ Остановить
              </button>
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      {messages.length === 1 && (
        <div className="suggestions">
          {SUGGESTIONS.map((s) => (
            <button key={s} className="chip" onClick={() => ask(s)}>{s}</button>
          ))}
        </div>
      )}

      <form
        className="chat-input"
        onSubmit={(e) => {
          e.preventDefault();
          ask();
        }}
      >
        <input
          autoFocus
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Спросите что-нибудь об архиве…"
          disabled={busy}
        />
        {busy ? (
          <button type="button" className="btn danger" onClick={stop}>
            ⏹ Стоп
          </button>
        ) : (
          <button className="btn primary" disabled={!input.trim()}>
            Отправить
          </button>
        )}
      </form>

      {selected && (
        <DocumentModal
          key={selected.id}
          doc={selected}
          onClose={() => setSelected(null)}
          onChanged={() => openSource(selected.id)}
          onOpenDocument={openSource}
        />
      )}
    </div>
  );
}
