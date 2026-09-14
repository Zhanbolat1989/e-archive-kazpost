const SECTIONS = [
  {
    icon: "📥",
    title: "Приём документов",
    body: "Загрузите файл или скан. Система проверит его антивирусом, сохранит "
      + "оригинал в неизменяемом хранилище (WORM), распознает текст (OCR) и "
      + "проиндексирует для поиска. ИИ автоматически составит аннотацию (опись) "
      + "документа. Статус обработки виден в списке документов в реальном времени.",
  },
  {
    icon: "🗂",
    title: "Дела и номенклатура",
    body: "Номенклатура дел задаёт индексы и сроки хранения по Перечню 279-НҚ. "
      + "Документы группируются в дела — единицы хранения. Срок хранения дела "
      + "рассчитывается автоматически, дата истечения отображается в списке.",
  },
  {
    icon: "📋",
    title: "Нормативные формы",
    body: "В карточке дела формируются: внутренняя опись документов дела "
      + "(прил. 28), лист-заверитель дела (прил. 31), опись электронного дела "
      + "с контрольными характеристиками и обложка дела. Каждая форма "
      + "выгружается в PDF и DOCX либо сохраняется обратно в архив.",
  },
  {
    icon: "🔁",
    title: "Изменение документа",
    body: "Оригинал в архиве неизменяем. Чтобы отразить изменение (например, "
      + "смену собственника недвижимости или переоформление кадастрового "
      + "паспорта), зарегистрируйте новую версию кнопкой «Заменить документ» — "
      + "предыдущая версия пометится заменённой, а история версий сохранится.",
  },
  {
    icon: "📤",
    title: "Выдача дел",
    body: "Заказ на выдачу → акт выдачи во временное пользование (прил. 20–22) "
      + "→ отметка о возврате. Просроченные возвраты подсвечиваются в списке "
      + "и попадают в сводный отчет по запросам.",
  },
  {
    icon: "🗑",
    title: "Экспертиза ценности и уничтожение",
    body: "Документы с истёкшим сроком хранения отбираются в акт о выделении "
      + "к уничтожению (прил. 14/15). Акт утверждает администратор; после "
      + "утверждения документы помечаются уничтоженными и исключаются из поиска "
      + "и сводных отчётов.",
  },
  {
    icon: "🤖",
    title: "ИИ-ассистент",
    body: "Задавайте вопросы обычным языком: «сколько договоров с ТОО X», "
      + "«кто текущий собственник объекта», «какие дела истекают». Агент сам "
      + "ищет по содержимому и метаданным и отвечает со ссылками на документы.",
  },
  {
    icon: "🏢",
    title: "Предприятие",
    body: "Сведения об организации, организационная структура и подписанты. "
      + "Оргструктура используется при построении маршрутов согласования "
      + "карточек дел и документов.",
  },
  {
    icon: "📊",
    title: "Отчеты",
    body: "Сводные отчеты по делам, документам, запросам на выдачу и актам "
      + "на уничтожение. Любой отчет выгружается в CSV для передачи "
      + "или дальнейшей обработки.",
  },
  {
    icon: "🔐",
    title: "Безопасность",
    body: "Вход подтверждается кодом при работе с нового устройства. После трёх "
      + "неверных попыток учётная запись блокируется. Все действия фиксируются "
      + "в аудиторском следе с указанием IP и результата; журнал выгружается "
      + "для SIEM и не подлежит удалению — только переносу в архив.",
  },
];

import { useEffect, useState } from "react";
import { api } from "../api.js";

// Обращение в службу поддержки (ТЗ АГП п. 8, модуль «Помощь»).
function SupportForm() {
  const [form, setForm] = useState({ subject: "", body: "" });
  const [tickets, setTickets] = useState([]);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");

  function load() {
    api.listTickets({ mine: true }).then(setTickets).catch(() => {});
  }
  useEffect(load, []);

  async function submit(e) {
    e.preventDefault();
    setError("");
    try {
      await api.createTicket(form);
      setForm({ subject: "", body: "" });
      setSent(true);
      load();
    } catch (e2) { setError(e2.message); }
  }

  return (
    <div className="card dash-card wide" style={{ marginTop: 18 }}>
      <h3 style={{ marginTop: 0 }}>Обращение в службу поддержки</h3>
      <p className="muted">
        Опишите ошибку или вопрос — обращение попадёт администратору системы.
        Для инцидентов информационной безопасности укажите в теме пометку
        «инцидент ИБ».
      </p>
      {error && <div className="alert error">{error}</div>}
      {sent && <div className="alert success">Обращение зарегистрировано.</div>}
      <form className="form" onSubmit={submit}>
        <label>Тема</label>
        <input value={form.subject} required
               onChange={(e) => setForm({ ...form, subject: e.target.value })}
               placeholder="кратко о проблеме" />
        <label>Описание</label>
        <textarea rows={4} value={form.body}
                  onChange={(e) => setForm({ ...form, body: e.target.value })}
                  placeholder="что произошло, в каком разделе, что ожидалось" />
        <button className="btn primary" style={{ marginTop: 12 }}>Отправить</button>
      </form>

      {tickets.length > 0 && (
        <>
          <h4 style={{ marginBottom: 6 }}>Мои обращения</h4>
          <table className="grid">
            <thead>
              <tr><th>Дата</th><th>Тема</th><th>Статус</th><th>Ответ</th></tr>
            </thead>
            <tbody>
              {tickets.map((t) => (
                <tr key={t.id}>
                  <td className="muted">{new Date(t.created_at).toLocaleDateString("ru-RU")}</td>
                  <td>{t.subject}</td>
                  <td><span className="type-tag">{t.status}</span></td>
                  <td className="muted">{t.answer || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </div>
  );
}

export default function Help() {
  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h1>Помощь</h1>
          <p className="muted">Справочная информация об использовании системы</p>
        </div>
      </header>

      <div className="dash-grid">
        {SECTIONS.map((s) => (
          <div className="card dash-card" key={s.title}>
            <h3 style={{ marginTop: 0 }}>{s.icon} {s.title}</h3>
            <p className="muted" style={{ marginBottom: 0, lineHeight: 1.5 }}>{s.body}</p>
          </div>
        ))}
      </div>

      <div className="card dash-card wide" style={{ marginTop: 18 }}>
        <h3 style={{ marginTop: 0 }}>Нормативная база</h3>
        <ul className="muted" style={{ lineHeight: 1.8, marginBottom: 0 }}>
          <li>Приказ МКС РК № 235 — правила приёма, хранения, учёта и использования документов НАФ</li>
          <li>Приказ МКС РК № 236 — правила документирования и использования систем ЭДО (ЭРКК, номенклатура)</li>
          <li>Перечень типовых документов 279-НҚ — сроки хранения</li>
          <li>Закон РК № 310-III — государственная регистрация прав на недвижимое имущество</li>
          <li>Закон РК «О Национальном архивном фонде и архивах»</li>
        </ul>
      </div>

      <SupportForm />
    </div>
  );
}
