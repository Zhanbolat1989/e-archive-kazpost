# -*- coding: utf-8 -*-
"""Генерация нормативных архивных форм (двуязычные қаз/рус).

Формы по правилам РК:
  * internal_opis — Внутренняя опись документов дела (прил. 28 к приказу МКС № 235);
  * zaverit      — Лист-заверитель дела (прил. 31 к приказу МКС № 235);
  * e_opis       — Опись электронного дела (файлы, байты, контрольные
                   характеристики SHA-256 — по приказу МКС № 236);
  * cover        — Обложка дела.

Поля, которые система не отслеживает (номера бумажных листов), оставляются
для ручного заполнения — как в типографских бланках.
"""
import html
import io
from datetime import date

from ..models import Case, Document
from .numword import num_to_words_ru, num_to_words_kz

ORG_NAME = "ТОО «Цифровой Архив»"  # TODO: вынести в настройки организации

_CSS = """
@page { size: A4; margin: 20mm 15mm; }
body { font-family: 'DejaVu Sans', sans-serif; font-size: 11pt; color: #000; }
h1 { font-size: 13pt; text-align: center; margin: 4px 0; }
h2 { font-size: 11pt; text-align: center; font-weight: normal; margin: 2px 0 14px; }
table { width: 100%; border-collapse: collapse; margin-top: 10px; }
th, td { border: 1px solid #000; padding: 4px 6px; font-size: 10pt; vertical-align: top; }
th { text-align: center; background: #f0f0f0; }
.kz { font-style: italic; }
.meta { margin: 3px 0; }
.sign { margin-top: 28px; display: flex; justify-content: space-between; }
.total { margin-top: 12px; }
.blank { display: inline-block; min-width: 120px; border-bottom: 1px solid #000; }
.center { text-align: center; }
.small { font-size: 9pt; color: #333; }
.right { text-align: right; }
.appendix { text-align: right; font-size: 9pt; margin-bottom: 8px; }
"""


def _esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def _fmt_d(d: date | None) -> str:
    return d.strftime("%d.%m.%Y") if d else "—"


def _page(title: str, body: str) -> str:
    return (f"<!doctype html><html><head><meta charset='utf-8'>"
            f"<title>{_esc(title)}</title><style>{_CSS}</style></head>"
            f"<body>{body}</body></html>")


def _case_header(case: Case) -> str:
    return (
        f"<div class='meta center'><b>{_esc(ORG_NAME)}</b></div>"
        f"<div class='meta center'>Іс индексі / Индекс дела: <b>{_esc(case.index or '—')}</b>"
        f" · Том {case.volume} · {case.year} ж./г.</div>"
        f"<div class='meta center'>{_esc(case.title)}</div>"
    )


# ---------- Прил. 28: внутренняя опись ----------
def internal_opis_html(case: Case, docs: list[Document]) -> str:
    n = len(docs)
    rows = "".join(
        f"<tr><td class='center'>{i + 1}</td>"
        f"<td>{_esc(d.doc_number or '—')}</td>"
        f"<td class='center'>{_fmt_d(d.doc_date)}</td>"
        f"<td>{_esc(d.title)}</td>"
        f"<td class='center'></td>"
        f"<td></td></tr>"
        for i, d in enumerate(docs)
    )
    body = (
        "<div class='appendix'>Приложение 28 к Правилам приема, хранения, учета и "
        "использования документов НАФ (приказ МКС РК № 235 от 25.08.2023)</div>"
        "<h1>ІС ҚҰЖАТТАРЫНЫҢ ІШКІ ТІЗІМДЕМЕСІ</h1>"
        "<h2>ВНУТРЕННЯЯ ОПИСЬ документов дела</h2>"
        + _case_header(case) +
        "<table><thead><tr>"
        "<th>№ р/с<br/><span class='kz'>№ п/п</span></th>"
        "<th>Құжат индексі<br/><span class='kz'>Индекс (номер) документа</span></th>"
        "<th>Күні<br/><span class='kz'>Дата</span></th>"
        "<th>Құжаттың тақырыбы<br/><span class='kz'>Заголовок документа</span></th>"
        "<th>Парақ нөмірлері<br/><span class='kz'>Номера листов</span></th>"
        "<th>Ескертпе<br/><span class='kz'>Примечание</span></th>"
        f"</tr></thead><tbody>{rows}</tbody></table>"
        f"<p class='total'>Барлығы / Итого: <b>{n}</b> "
        f"({num_to_words_kz(n)} / {num_to_words_ru(n)}) құжат / документ(ов).</p>"
        "<p>Ішкі тізімдеме парақтарының саны / Количество листов внутренней описи: "
        "<span class='blank'></span></p>"
        "<div class='sign'><span>Лауазымы / Должность: <span class='blank'></span></span>"
        "<span>Қолы / Подпись: <span class='blank'></span></span>"
        f"<span>Күні / Дата: {date.today().strftime('%d.%m.%Y')}</span></div>"
    )
    return _page("Внутренняя опись", body)


# ---------- Прил. 31: лист-заверитель ----------
def zaverit_html(case: Case, docs: list[Document]) -> str:
    n = len(docs)
    body = (
        "<div class='appendix'>Приложение 31 к Правилам приема, хранения, учета и "
        "использования документов НАФ (приказ МКС РК № 235 от 25.08.2023)</div>"
        "<h1>ІСТІ РАСТАУ ПАРАҒЫ</h1>"
        "<h2>ЛИСТ-ЗАВЕРИТЕЛЬ дела</h2>"
        + _case_header(case) +
        "<p class='total'>Іске тігілген және нөмірленген / В деле подшито и пронумеровано "
        "<span class='blank'></span> (<span class='blank'></span>) парақ / лист(ов),</p>"
        "<p>оның ішінде: әріпті парақ нөмірлері / в том числе: литерные номера листов "
        "<span class='blank'></span>; өткізілген нөмірлер / пропущенные номера "
        "<span class='blank'></span></p>"
        "<p>+ ішкі тізімдеме парақтары / листов внутренней описи "
        "<span class='blank'></span> (<span class='blank'></span>)</p>"
        f"<p class='small'>Анықтама: істегі құжаттар саны / Справочно: документов в деле — "
        f"<b>{n}</b> ({num_to_words_kz(n)} / {num_to_words_ru(n)}).</p>"
        "<table><thead><tr>"
        "<th>Істі ресімдеудің ерекшеліктері<br/>"
        "<span class='kz'>Особенности формирования, оформления и физического состояния "
        "документов дела</span></th>"
        "<th>Парақ нөмірлері<br/><span class='kz'>Номера листов</span></th>"
        "</tr></thead><tbody>"
        "<tr><td style='height:70px'></td><td></td></tr>"
        "</tbody></table>"
        "<div class='sign'><span>Лауазымы / Должность: <span class='blank'></span></span>"
        "<span>Қолы / Подпись: <span class='blank'></span></span>"
        f"<span>Күні / Дата: {date.today().strftime('%d.%m.%Y')}</span></div>"
    )
    return _page("Лист-заверитель", body)


# ---------- Опись электронного дела (по № 236) ----------
def e_opis_html(case: Case, docs: list[Document]) -> str:
    total_bytes = sum(d.size or 0 for d in docs)
    rows = "".join(
        f"<tr><td class='center'>{i + 1}</td>"
        f"<td>{_esc(d.doc_number or '—')}</td>"
        f"<td class='center'>{_fmt_d(d.doc_date)}</td>"
        f"<td>{_esc(d.title)}</td>"
        f"<td class='center'>1</td>"
        f"<td class='right'>{d.size or 0}</td>"
        f"<td class='small'>{_esc(d.checksum_sha256)}</td>"
        f"<td></td></tr>"
        for i, d in enumerate(docs)
    )
    body = (
        "<div class='appendix'>Опись электронного дела (Правила документирования и "
        "управления документацией, приказ МКС РК № 236 от 25.08.2023)</div>"
        "<h1>ЭЛЕКТРОНДЫҚ ІС ТІЗІМДЕМЕСІ</h1>"
        "<h2>ОПИСЬ электронного дела</h2>"
        + _case_header(case) +
        "<table><thead><tr>"
        "<th>№</th>"
        "<th>Құжат нөмірі<br/><span class='kz'>Номер документа</span></th>"
        "<th>Күні<br/><span class='kz'>Дата</span></th>"
        "<th>Тақырыбы<br/><span class='kz'>Заголовок</span></th>"
        "<th>Файлдар саны<br/><span class='kz'>Кол-во файлов</span></th>"
        "<th>Көлемі (байт)<br/><span class='kz'>Объём (байт)</span></th>"
        "<th>Бақылау сипаттамасы (SHA-256)<br/><span class='kz'>Контрольная "
        "характеристика</span></th>"
        "<th>Ескертпе<br/><span class='kz'>Примечание</span></th>"
        f"</tr></thead><tbody>{rows}</tbody></table>"
        f"<p class='total'>Барлығы / Итого: <b>{len(docs)}</b> құжат / документ(ов), "
        f"<b>{len(docs)}</b> сақтау объектісі / объект(ов) хранения, "
        f"жалпы көлемі / общий объём — <b>{total_bytes}</b> байт.</p>"
        "<div class='sign'><span>Лауазымы / Должность: <span class='blank'></span></span>"
        "<span>Қолы / Подпись: <span class='blank'></span></span>"
        f"<span>Күні / Дата: {date.today().strftime('%d.%m.%Y')}</span></div>"
    )
    return _page("Опись электронного дела", body)


# ---------- Обложка дела ----------
def cover_html(case: Case, docs: list[Document]) -> str:
    retention = "Тұрақты / Постоянно" if case.permanent else (case.retention_label or "—")
    body = (
        f"<div style='margin-top:40mm'></div>"
        f"<h2>{_esc(ORG_NAME)}</h2>"
        f"<div style='margin-top:22mm'></div>"
        f"<h1>ІС / ДЕЛО № {_esc(case.index or '—')} · ТОМ {case.volume}</h1>"
        f"<h2 style='margin-top:10mm'>{_esc(case.title)}</h2>"
        f"<div style='margin-top:24mm'></div>"
        f"<p class='center'>Басталды / Начато: <b>{_fmt_d(case.date_from)}</b></p>"
        f"<p class='center'>Аяқталды / Окончено: <b>{_fmt_d(case.date_to)}</b></p>"
        f"<p class='center'>Құжаттар саны / Документов: <b>{len(docs)}</b></p>"
        f"<p class='center'>Сақтау мерзімі / Срок хранения: <b>{_esc(retention)}</b></p>"
        + (f"<p class='center'>Сақталуы тиіс / Хранить до: "
           f"<b>{_fmt_d(case.retention_until)}</b></p>" if not case.permanent else "")
    )
    return _page(f"Обложка дела {case.index}", body)


# ---------- Прил. 14/15: акт о выделении к уничтожению ----------
def destruction_act_html(act, docs: list[Document]) -> str:
    kind = "ЭЛЕКТРОНДЫҚ ҚҰЖАТТАРДЫ" if act.is_electronic else "ҚҰЖАТТАРДЫ"
    kind_ru = "электронных документов" if act.is_electronic else "документов"
    appendix = "15" if act.is_electronic else "14"
    n = len(docs)
    rows = "".join(
        f"<tr><td class='center'>{i + 1}</td>"
        f"<td>{_esc(d.doc_number or '—')}</td>"
        f"<td class='center'>{_fmt_d(d.doc_date)}</td>"
        f"<td>{_esc(d.title)}</td>"
        f"<td class='center'>{_esc(d.retention_label or '—')}</td>"
        f"<td class='center'>{_fmt_d(d.retention_until)}</td>"
        + (f"<td class='small'>{_esc(d.checksum_sha256[:16])}…</td>"
           if act.is_electronic else "")
        + "</tr>"
        for i, d in enumerate(docs)
    )
    extra_col = ("<th>Бақылау сипаттамасы<br/><span class='kz'>Контрольная "
                 "характеристика</span></th>" if act.is_electronic else "")
    status_note = ("" if act.status.value == "Утверждён" else
                   "<p class='center' style='color:#a00'><b>ЖОБА / ПРОЕКТ</b></p>")
    body = (
        f"<div class='appendix'>Приложение {appendix} к Правилам приема, хранения, "
        "учета и использования документов НАФ (приказ МКС РК № 235 от 25.08.2023)</div>"
        f"<h1>{kind} ЖОЮҒА БӨЛУ ТУРАЛЫ АКТ № {_esc(act.number)}</h1>"
        f"<h2>АКТ о выделении к уничтожению {kind_ru} № {_esc(act.number)} "
        f"от {act.act_date.strftime('%d.%m.%Y')}</h2>"
        + status_note +
        f"<div class='meta center'><b>{_esc(ORG_NAME)}</b></div>"
        "<p>Сақтау мерзімі өткен, ғылыми-тарихи құндылығы жоқ құжаттар жоюға "
        "бөлінді / На основании истечения сроков хранения отобраны к уничтожению "
        "документы, не имеющие научно-исторической ценности:</p>"
        "<table><thead><tr>"
        "<th>№</th>"
        "<th>Құжат нөмірі<br/><span class='kz'>Номер</span></th>"
        "<th>Күні<br/><span class='kz'>Дата</span></th>"
        "<th>Тақырыбы<br/><span class='kz'>Заголовок</span></th>"
        "<th>Сақтау мерзімі<br/><span class='kz'>Срок хранения</span></th>"
        "<th>Мерзімі өткен күні<br/><span class='kz'>Срок истёк</span></th>"
        f"{extra_col}"
        f"</tr></thead><tbody>{rows}</tbody></table>"
        f"<p class='total'>Барлығы / Итого: <b>{n}</b> "
        f"({num_to_words_kz(n)} / {num_to_words_ru(n)}) құжат / документ(ов).</p>"
        + (f"<p>Ескертпе / Примечание: {_esc(act.note)}</p>" if act.note else "") +
        f"<div class='sign'><span>Жасады / Составил: {_esc(act.created_by)}</span>"
        + (f"<span>Бекітті / Утвердил: {_esc(act.approved_by)}</span>"
           if act.approved_by else
           "<span>Бекітті / Утвердил: <span class='blank'></span></span>")
        + f"<span>Күні / Дата: {act.act_date.strftime('%d.%m.%Y')}</span></div>"
    )
    return _page(f"Акт {act.number}", body)


def destruction_act_pdf(act, docs: list[Document]) -> bytes:
    from weasyprint import HTML

    return HTML(string=destruction_act_html(act, docs)).write_pdf()


# ---------- Прил. 21: акт выдачи дел во временное пользование ----------
def issue_act_html(issue, case: Case) -> str:
    body = (
        "<div class='appendix'>Приложение 21 к Правилам приема, хранения, учета и "
        "использования документов НАФ (приказ МКС РК № 235 от 25.08.2023)</div>"
        "<h1>ІСТЕРДІ УАҚЫТША ПАЙДАЛАНУҒА БЕРУ ТУРАЛЫ АКТ</h1>"
        "<h2>АКТ о выдаче дел во временное пользование</h2>"
        f"<div class='meta center'><b>{_esc(ORG_NAME)}</b></div>"
        f"<p>Іс / Дело: <b>{_esc(case.index or '—')}</b> · Том {case.volume} · "
        f"{case.year} ж./г. — {_esc(case.title)}</p>"
        f"<p>Кімге берілді / Кому выдано: <b>{_esc(issue.requested_by)}</b></p>"
        f"<p>Мақсаты / Цель использования: {_esc(issue.purpose or '—')}</p>"
        f"<p>Берілген күні / Дата выдачи: <b>{_fmt_d(issue.issue_date)}</b> · "
        f"Қайтару мерзімі / Срок возврата: <b>{_fmt_d(issue.due_date)}</b></p>"
        + (f"<p>Қайтарылды / Возвращено: <b>{_fmt_d(issue.returned_at)}</b></p>"
           if issue.returned_at else "") +
        "<p class='small'>Пайдаланушы істің сақталуына жауап береді / Пользователь "
        "несёт ответственность за сохранность дела.</p>"
        "<div class='sign'><span>Берді / Выдал: <span class='blank'></span></span>"
        "<span>Алды / Получил: <span class='blank'></span></span>"
        f"<span>Күні / Дата: {date.today().strftime('%d.%m.%Y')}</span></div>"
    )
    return _page("Акт выдачи", body)


def issue_act_pdf(issue, case: Case) -> bytes:
    from weasyprint import HTML

    return HTML(string=issue_act_html(issue, case)).write_pdf()


# ---------- Заверенная бумажная копия ЭД (п. 38/44 приказа № 236, ред. 2026) ----------
def certified_copy_html(doc: Document, sig_note: str) -> str:
    text = (doc.ocr_text or doc.description or "").strip()
    text_html = "<br/>".join(_esc(line) for line in text.splitlines()[:200])
    body = (
        f"<div class='meta center'><b>{_esc(ORG_NAME)}</b></div>"
        f"<h1>{_esc(doc.title)}</h1>"
        f"<div class='meta center'>№ {_esc(doc.doc_number or '—')} · "
        f"{_fmt_d(doc.doc_date)} · {_esc(doc.doc_type.value)}</div><hr/>"
        f"<div style='margin:14px 0'>{text_html}</div><hr/>"
        "<div style='border:2px solid #000; padding:10px 14px; margin-top:18px'>"
        "<p><b>Электрондық құжаттың көшірмесі дұрыс / "
        "Копия электронного документа верна</b></p>"
        f"<p class='small'>Нәтиже / Результат проверки ЭЦП: <b>{_esc(sig_note)}</b></p>"
        f"<p class='small'>SHA-256: {_esc(doc.checksum_sha256)}</p>"
        f"<p class='small'>Парақ саны / Количество листов: <span class='blank'></span></p>"
        "<p class='small'>Растаушының қолы / Подпись заверителя: "
        "<span class='blank'></span> &nbsp;&nbsp; Күні / Дата: "
        f"{date.today().strftime('%d.%m.%Y')}</p>"
        "</div>"
    )
    return _page(f"Заверенная копия {doc.doc_number}", body)


def certified_copy_pdf(doc: Document, sig_note: str) -> bytes:
    from weasyprint import HTML

    return HTML(string=certified_copy_html(doc, sig_note)).write_pdf()


# ---------- Прил. 1: акт миграции и перезаписи электронных документов ----------
def migration_act_html(docs: list[Document]) -> str:
    rows = "".join(
        f"<tr><td class='center'>{i + 1}</td><td>{_esc(d.doc_number or '—')}</td>"
        f"<td>{_esc(d.title)}</td><td class='center'>{_esc(d.content_type)}</td>"
        f"<td class='center'>PDF/A-1</td>"
        f"<td class='small'>{_esc(d.checksum_sha256[:20])}…</td></tr>"
        for i, d in enumerate(docs)
    )
    n = len(docs)
    body = (
        "<div class='appendix'>Приложение 1 к Правилам приема, хранения, учета и "
        "использования документов НАФ (приказ МКС РК № 235 от 25.08.2023)</div>"
        "<h1>ЭЛЕКТРОНДЫҚ ҚҰЖАТТАРДЫ КӨШІРУ ЖӘНЕ ҚАЙТА ЖАЗУ ТУРАЛЫ АКТ</h1>"
        "<h2>АКТ о миграции и перезаписи электронных документов</h2>"
        f"<div class='meta center'><b>{_esc(ORG_NAME)}</b> · "
        f"{date.today().strftime('%d.%m.%Y')}</div>"
        "<p>Тұрақты сақтау форматына көшірілді / Выполнена конвертация в формат "
        "постоянного хранения:</p>"
        "<table><thead><tr><th>№</th>"
        "<th>Нөмірі<br/><span class='kz'>Номер</span></th>"
        "<th>Тақырыбы<br/><span class='kz'>Заголовок</span></th>"
        "<th>Бастапқы формат<br/><span class='kz'>Исходный формат</span></th>"
        "<th>Жаңа формат<br/><span class='kz'>Новый формат</span></th>"
        "<th>Бақылау сипаттамасы<br/><span class='kz'>Контр. характеристика</span></th>"
        f"</tr></thead><tbody>{rows}</tbody></table>"
        f"<p class='total'>Барлығы / Итого: <b>{n}</b> "
        f"({num_to_words_kz(n)} / {num_to_words_ru(n)}) құжат / документ(ов). "
        "Түпнұсқалар WORM-қоймада сақталады / Оригиналы сохранены в WORM-хранилище.</p>"
        "<div class='sign'><span>Жасады / Составил: <span class='blank'></span></span>"
        "<span>Бекітті / Утвердил: <span class='blank'></span></span>"
        f"<span>Күні / Дата: {date.today().strftime('%d.%m.%Y')}</span></div>"
    )
    return _page("Акт миграции", body)


def migration_act_pdf(docs: list[Document]) -> bytes:
    from weasyprint import HTML

    return HTML(string=migration_act_html(docs)).write_pdf()


# ---------- Прил. 26: акт проверки наличия и состояния ----------
def inventory_check_act_html(results: list[dict]) -> str:
    ok = [r for r in results if r["ok"]]
    bad = [r for r in results if not r["ok"]]
    rows = "".join(
        f"<tr><td class='center'>{i + 1}</td><td>{_esc(r['number'] or '—')}</td>"
        f"<td>{_esc(r['title'])}</td>"
        f"<td class='center'>{'сәйкес / соответствует' if r['ok'] else '<b>СӘЙКЕС ЕМЕС / НЕ СООТВЕТСТВУЕТ</b>'}</td>"
        f"<td class='small'>{_esc(r['note'])}</td></tr>"
        for i, r in enumerate(results)
    )
    body = (
        "<div class='appendix'>Приложение 26 к Правилам приема, хранения, учета и "
        "использования документов НАФ (приказ МКС РК № 235 от 25.08.2023)</div>"
        "<h1>ҚҰЖАТТАРДЫҢ БАР-ЖОҒЫН ЖӘНЕ ЖАЙ-КҮЙІН ТЕКСЕРУ АКТІСІ</h1>"
        "<h2>АКТ проверки наличия и состояния архивных документов</h2>"
        f"<div class='meta center'><b>{_esc(ORG_NAME)}</b> · "
        f"{date.today().strftime('%d.%m.%Y')}</div>"
        f"<p>Тексерілді / Проверено: <b>{len(results)}</b> құжат / документ(ов); "
        f"сәйкес / соответствует: <b>{len(ok)}</b>; "
        f"сәйкес емес / не соответствует: <b>{len(bad)}</b>.</p>"
        "<p class='small'>Тексеру әдісі / Метод: сверка контрольной характеристики "
        "SHA-256 каталога с объектом в WORM-хранилище.</p>"
        "<table><thead><tr><th>№</th>"
        "<th>Нөмірі<br/><span class='kz'>Номер</span></th>"
        "<th>Тақырыбы<br/><span class='kz'>Заголовок</span></th>"
        "<th>Жай-күйі<br/><span class='kz'>Состояние</span></th>"
        "<th>Ескертпе<br/><span class='kz'>Примечание</span></th>"
        f"</tr></thead><tbody>{rows}</tbody></table>"
        "<div class='sign'><span>Тексерді / Проверил: <span class='blank'></span></span>"
        "<span>Қолы / Подпись: <span class='blank'></span></span>"
        f"<span>Күні / Дата: {date.today().strftime('%d.%m.%Y')}</span></div>"
    )
    return _page("Акт проверки наличия", body)


def inventory_check_act_pdf(results: list[dict]) -> bytes:
    from weasyprint import HTML

    return HTML(string=inventory_check_act_html(results)).write_pdf()


FORMS = {
    "internal_opis": ("Внутренняя опись (прил. 28)", internal_opis_html),
    "zaverit": ("Лист-заверитель (прил. 31)", zaverit_html),
    "e_opis": ("Опись электронного дела", e_opis_html),
    "cover": ("Обложка дела", cover_html),
}


def render_html(kind: str, case: Case, docs: list[Document]) -> str:
    _, fn = FORMS[kind]
    return fn(case, docs)


def render_pdf(kind: str, case: Case, docs: list[Document]) -> bytes:
    from weasyprint import HTML

    return HTML(string=render_html(kind, case, docs)).write_pdf()


def render_docx(kind: str, case: Case, docs: list[Document]) -> bytes:
    """Упрощённый DOCX-вариант (таблица с теми же графами)."""
    from docx import Document as Docx
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    title, _ = FORMS[kind]
    doc = Docx()
    h = doc.add_paragraph()
    h.alignment = WD_ALIGN_PARAGRAPH.CENTER
    h.add_run(title.upper()).bold = True
    doc.add_paragraph(f"{ORG_NAME} · Дело {case.index or '—'} · Том {case.volume} · {case.year} г.")
    doc.add_paragraph(case.title)

    if kind in ("internal_opis", "e_opis"):
        if kind == "internal_opis":
            headers = ["№", "Индекс/номер", "Дата", "Заголовок", "Листы", "Примечание"]
        else:
            headers = ["№", "Номер", "Дата", "Заголовок", "Файлов", "Байт",
                       "SHA-256", "Примечание"]
        table = doc.add_table(rows=1, cols=len(headers))
        table.style = "Table Grid"
        for i, htxt in enumerate(headers):
            table.rows[0].cells[i].text = htxt
        for i, d in enumerate(docs, 1):
            row = table.add_row().cells
            if kind == "internal_opis":
                vals = [str(i), d.doc_number or "—", _fmt_d(d.doc_date), d.title, "", ""]
            else:
                vals = [str(i), d.doc_number or "—", _fmt_d(d.doc_date), d.title,
                        "1", str(d.size or 0), d.checksum_sha256, ""]
            for j, v in enumerate(vals):
                row[j].text = v
        n = len(docs)
        doc.add_paragraph(
            f"Итого: {n} ({num_to_words_ru(n)}) документ(ов)."
        )
    elif kind == "zaverit":
        n = len(docs)
        doc.add_paragraph("В деле подшито и пронумеровано ______ (________________) листов,")
        doc.add_paragraph("в том числе: литерные номера листов ______; пропущенные номера ______")
        doc.add_paragraph("+ листов внутренней описи ______ (________________)")
        doc.add_paragraph(f"Справочно: документов в деле — {n} ({num_to_words_ru(n)}).")
    else:  # cover
        doc.add_paragraph(f"Начато: {_fmt_d(case.date_from)} · Окончено: {_fmt_d(case.date_to)}")
        doc.add_paragraph(
            "Срок хранения: " + ("Постоянно" if case.permanent else case.retention_label or "—")
        )

    doc.add_paragraph("")
    doc.add_paragraph(f"Должность ______________  Подпись ______________  Дата {date.today().strftime('%d.%m.%Y')}")
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
