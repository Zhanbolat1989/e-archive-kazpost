# -*- coding: utf-8 -*-
"""Печатные формы НТО и передачи дел (ТС-176 п. 5.3, 8.2): историческая
справка, предисловие к описи, акт о завершении работ по упорядочению, акт о
недостающих делах, акт приёма-передачи дел на государственное хранение.

Разделы, которых система не знает (история фондообразователя, причины утрат),
пишет архивариус; то, что система ведёт сама (дела, описи, этапы работ, акты
уничтожения), подставляется из базы. Реквизиты вне системы — пустые строки для
заполнения от руки, как в других нормативных формах.
"""
from . import nto as rules
from .forms import _esc, _fmt_d, _page
from .numword import num_to_words_kz, num_to_words_ru


def _paragraphs(text: str) -> str:
    parts = [p.strip() for p in (text or "").split("\n") if p.strip()]
    return "".join(f"<p>{_esc(p)}</p>" for p in parts) or "<p class='small'>—</p>"


def _sections(rec) -> str:
    fields = rec.fields or {}
    return "".join(f"<h3>{_esc(label)}</h3>{_paragraphs(fields.get(key, ''))}"
                   for key, label in rules.NTO_KINDS[rec.kind]["fields"])


def _years(rec) -> str:
    if rec.year_from and rec.year_to:
        return f"{rec.year_from}–{rec.year_to}"
    return str(rec.year_from or rec.year_to or "—")


def _draft(is_final: bool) -> str:
    return "" if is_final else "<p class='center' style='color:#a00'><b>ЖОБА / ПРОЕКТ</b></p>"


def _head(kz: str, ru: str, number: str, on: object, org: str, is_final: bool) -> str:
    no = f" № {_esc(number)}" if number else ""
    return (f"<div class='meta center'><b>{_esc(org)}</b></div>"
            f"<h1>{kz}{no}</h1><h2>{ru}{no} от {_fmt_d(on)}</h2>" + _draft(is_final))


def _decisions(decisions: list[str]) -> str:
    return "".join(f"<p>{_esc(d)}</p>" for d in decisions)


def _record_head(kz: str, ru: str, rec, org: str) -> str:
    return _head(kz, ru, rec.number, rec.record_date, org, rec.status == rules.APPROVED)


def _record_footer(rec, decisions: list[str]) -> str:
    approved = (f"<span>Бекітті / Утвердил: {_esc(rec.approved_by)}</span>" if rec.approved_by
                else "<span>Бекітті / Утвердил: <span class='blank'></span></span>")
    return (_decisions(decisions)
            + f"<div class='sign'><span>Жасады / Составил: {_esc(rec.created_by)}</span>"
            + approved + f"<span>Күні / Дата: {_fmt_d(rec.record_date)}</span></div>")


def _table(headers: list[str], rows: list[list], empty: str) -> str:
    head = "".join(f"<th>{h}</th>" for h in headers)
    if not rows:
        return f"<p class='small'>{_esc(empty)}</p>"
    body = "".join("<tr>" + "".join(f"<td>{_esc(v)}</td>" for v in row) + "</tr>" for row in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def _total(n: int, kz_unit: str, ru_unit: str) -> str:
    return (f"<p class='total'>Барлығы / Итого: <b>{n}</b> "
            f"({num_to_words_kz(n)} / {num_to_words_ru(n)}) {kz_unit} / {ru_unit}.</p>")


def history_note_html(rec, org: str, departments: list[str], stats: dict,
                      decisions: list[str]) -> str:
    structure = ("<h3>Құрылымы / Структура (по данным системы)</h3><ul>"
                 + "".join(f"<li>{_esc(n)}</li>" for n in departments) + "</ul>"
                 if departments else "")
    body = (
        _record_head("ТАРИХИ АНЫҚТАМА", "ИСТОРИЧЕСКАЯ СПРАВКА", rec, org)
        + f"<p class='meta'>Қор / Фонд: <b>{_esc(rec.fond or '—')}</b> · "
          f"Жылдар / Крайние даты: <b>{_years(rec)}</b></p>"
        + _sections(rec) + structure
        + "<h3>Сведения о документах фонда (по данным системы)</h3>"
        + f"<p>Дел на хранении: <b>{stats['cases']}</b>, в том числе постоянного хранения: "
          f"<b>{stats['permanent']}</b>; крайние годы дел: "
          f"{stats['year_min'] or '—'}–{stats['year_max'] or '—'}.</p>"
        + _record_footer(rec, decisions)
    )
    return _page(rec.title or "Историческая справка", body)


def inventory_preface_html(rec, org: str, inventory, stats: dict,
                           decisions: list[str]) -> str:
    inv = (f"<p class='meta'>Тізімдеме / Опись № <b>{_esc(inventory.number)}</b> — "
           f"{_esc(inventory.title)} ({_esc(inventory.kind)})</p>" if inventory else "")
    n = stats["cases"]
    body = (
        _record_head("ТІЗІМДЕМЕГЕ АЛҒЫСӨЗ", "ПРЕДИСЛОВИЕ К ОПИСИ", rec, org)
        + inv + _sections(rec)
        + "<h3>Объём описи (по данным системы)</h3>"
        + f"<p>В опись включено дел: <b>{n}</b> ({num_to_words_ru(n)}); крайние годы: "
          f"{stats['year_min'] or '—'}–{stats['year_max'] or '—'}.</p>"
        + _record_footer(rec, decisions)
    )
    return _page(rec.title or "Предисловие к описи", body)


def arrangement_act_html(rec, org: str, inventories: list[dict], stages: dict,
                         destroyed: list[dict], decisions: list[str]) -> str:
    inv_rows = [[i + 1, x["number"], x["title"], x["kind"], x["year"], x["cases"]]
                for i, x in enumerate(inventories)]
    act_rows = [[i + 1, x["number"], _fmt_d(x["date"]), x["documents"]]
                for i, x in enumerate(destroyed)]
    body = (
        _record_head("ҚҰЖАТТАРДЫ РЕТКЕ КЕЛТІРУ ЖҰМЫСТАРЫН АЯҚТАУ ТУРАЛЫ АКТ",
                     "АКТ о завершении работ по упорядочению документов", rec, org)
        + f"<p class='meta'>Қор / Фонд: <b>{_esc(rec.fond or '—')}</b> · "
          f"Жылдар / Период: <b>{_years(rec)}</b></p>"
        + f"<p>Научно-техническая обработка проведена по <b>{stages['cases']}</b> "
          f"делам, листов: <b>{stages['pages']}</b>.</p>"
        + "<h3>Составленные описи</h3>"
        + _table(["№", "Номер описи", "Заголовок", "Категория", "Год", "Дел"],
                 inv_rows, "Описей за период нет.")
        + "<h3>Акты о выделении к уничтожению, утверждённые за период</h3>"
        + _table(["№", "Номер акта", "Дата", "Документов"], act_rows,
                 "Актов за период нет.")
        + _sections(rec)
        + _record_footer(rec, decisions)
    )
    return _page(rec.title or "Акт о завершении работ по упорядочению", body)


def missing_act_html(rec, org: str, decisions: list[str]) -> str:
    items = rec.items or []
    rows = [[i + 1, x.get("case_index") or "—", x.get("title", ""), x.get("years") or "—",
             x.get("note") or ""] for i, x in enumerate(items)]
    body = (
        _record_head("ЖЕТІСПЕЙТІН ІСТЕР ТУРАЛЫ АКТ", "АКТ о недостающих делах", rec, org)
        + f"<p class='meta'>Қор / Фонд: <b>{_esc(rec.fond or '—')}</b></p>"
        + "<p>Проверкой наличия установлено отсутствие следующих дел:</p>"
        + _table(["№", "Индекс дела", "Заголовок дела", "Крайние даты", "Примечание"],
                 rows, "Дела не указаны.")
        + _total(len(items), "іс", "дел(а)")
        + _sections(rec)
        + _record_footer(rec, decisions)
    )
    return _page(rec.title or "Акт о недостающих делах", body)


def transfer_act_html(act, org: str, items: list[dict], decisions: list[str]) -> str:
    rows = [[x["order_no"], x["case_index"] or "—", x["case_title"], x["volume"],
             x["year"] or "—", x["documents_count"], x["retention"] or "—"] for x in items]
    documents = sum(x["documents_count"] for x in items)
    body = (
        _head("ІСТЕРДІ МЕМЛЕКЕТТІК САҚТАУҒА ҚАБЫЛДАУ-ТАПСЫРУ АКТІСІ",
              "АКТ приёма-передачи дел на государственное хранение",
              act.number, act.act_date, org, act.status == rules.TRANSFER_DONE)
        + f"<p>Тапсырады / Передаёт: <b>{_esc(org)}</b></p>"
        + f"<p>Қабылдайды / Принимает: <b>{_esc(act.archive_name)}</b></p>"
        + (f"<p>Қор / Фонд: <b>{_esc(act.fond)}</b></p>" if act.fond else "")
        + (f"<p>Негізі / Основание: {_esc(act.basis)}</p>" if act.basis else "")
        + _table(["№", "Индекс дела", "Заголовок дела", "Том", "Год", "Документов",
                  "Срок хранения"], rows, "Дела не указаны.")
        + _total(len(items), "іс", "дел(а)")
        + f"<p>Документов в делах: <b>{documents}</b>. Электронные дела передаются "
          "информационным пакетом с контрольными характеристиками файлов (SHA-256).</p>"
        + _decisions(decisions)
        + (f"<p>Ескертпе / Примечание: {_esc(act.note)}</p>" if act.note else "")
        + "<div class='sign'><span>Тапсырды / Сдал: <span class='blank'></span></span>"
          "<span>Қабылдады / Принял: <span class='blank'></span></span>"
          f"<span>Күні / Дата: {_fmt_d(act.act_date)}</span></div>"
    )
    return _page(f"Акт приёма-передачи {act.number}", body)


def to_pdf(html: str) -> bytes:
    from weasyprint import HTML

    return HTML(string=html).write_pdf()
