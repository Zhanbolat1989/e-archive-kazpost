# -*- coding: utf-8 -*-
"""Печатный пакет дела: все документы дела единым PDF, готовым к печати —
титульный лист + разделительный лист перед каждым документом + сам документ
(конвертированный в PDF, если это не PDF изначально)."""
import io
import logging

from pypdf import PdfReader, PdfWriter
from PIL import Image
from weasyprint import HTML

from ..models import Case, Document
from .forms import _esc, _page, _CSS, _fmt_d, ORG_NAME  # noqa: F401 (переиспользуем стиль форм)

log = logging.getLogger("printpack")


def _cover_pdf(case: Case, docs: list[Document]) -> bytes:
    body = (
        f"<div style='margin-top:50mm'></div>"
        f"<h2>{_esc(ORG_NAME)}</h2>"
        f"<div style='margin-top:16mm'></div>"
        f"<h1>ДЕЛО № {_esc(case.index or '—')} · ТОМ {case.volume}</h1>"
        f"<h2 style='margin-top:8mm'>{_esc(case.title)}</h2>"
        f"<div style='margin-top:20mm'></div>"
        f"<p class='center'>Документов в пакете: <b>{len(docs)}</b></p>"
        f"<p class='center'>Сформировано для печати: <b>{__import__('datetime').date.today().strftime('%d.%m.%Y')}</b></p>"
    )
    return HTML(string=_page(f"Дело {case.index}", body)).write_pdf()


def _separator_pdf(index: int, total: int, doc: Document) -> bytes:
    body = (
        f"<div style='margin-top:60mm'></div>"
        f"<p class='center small'>Документ {index} из {total}</p>"
        f"<h1 style='margin-top:6mm'>{_esc(doc.title)}</h1>"
        f"<p class='center' style='margin-top:6mm'>"
        f"№ {_esc(doc.doc_number or '—')} · {_fmt_d(doc.doc_date)} · {_esc(doc.doc_type.value)}</p>"
    )
    return HTML(string=_page(doc.title, body)).write_pdf()


def _to_pdf_bytes(data: bytes, content_type: str) -> bytes | None:
    """Приводит содержимое документа к PDF-странице(ам). None — если формат
    не поддерживается для печати (документ пропускается с записью в лог)."""
    ct = (content_type or "").lower()
    if ct == "application/pdf" or ct.endswith("pdf"):
        return data
    if ct.startswith("image/"):
        img = Image.open(io.BytesIO(data)).convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="PDF")
        return buf.getvalue()
    if ct.startswith("text/"):
        text = data.decode("utf-8", errors="ignore")
        lines = "<br/>".join(_esc(line) for line in text.splitlines())
        body = f"<div style='white-space:pre-wrap'>{lines}</div>"
        return HTML(string=_page("Документ", body)).write_pdf()
    return None


def build_print_pack(case: Case, docs: list[Document],
                     fetch) -> tuple[bytes, list[str]]:
    """fetch(storage_key) -> bytes. Возвращает (итоговый PDF, список
    пропущенных документов с причиной) — печать не должна падать целиком
    из-за одного нечитаемого файла."""
    writer = PdfWriter()
    skipped: list[str] = []

    for reader_bytes in (_cover_pdf(case, docs),):
        for page in PdfReader(io.BytesIO(reader_bytes)).pages:
            writer.add_page(page)

    for i, doc in enumerate(docs, 1):
        try:
            sep = _separator_pdf(i, len(docs), doc)
            for page in PdfReader(io.BytesIO(sep)).pages:
                writer.add_page(page)
        except Exception as exc:  # noqa: BLE001
            log.warning("Separator page failed for %s: %s", doc.id, exc)

        try:
            raw = fetch(doc.storage_key)
            pdf_bytes = _to_pdf_bytes(raw, doc.content_type)
            if pdf_bytes is None:
                skipped.append(f"{doc.title} — формат «{doc.content_type}» не поддерживается для печати")
                continue
            for page in PdfReader(io.BytesIO(pdf_bytes)).pages:
                writer.add_page(page)
        except Exception as exc:  # noqa: BLE001
            skipped.append(f"{doc.title} — ошибка чтения: {exc}")
            log.warning("Print pack: skipped %s (%s)", doc.id, exc)

    out = io.BytesIO()
    writer.write(out)
    return out.getvalue(), skipped
