"""Выгрузка реестров в Excel (описи дел, сводная номенклатура,
перечни к уничтожению «выгружаются в Excel»).

Один общий построитель таблицы: у всех выгрузок одинаковые требования —
заголовок листа, шапка, автоширина колонок и закреплённая первая строка.
"""
import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

_HEAD_FILL = PatternFill("solid", fgColor="E8EDF3")
_THIN = Side(style="thin", color="B6C2CF")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)
MAX_WIDTH = 60


def build(title: str, headers: list[str], rows: list[list],
          sheet: str = "Лист1", subtitle: str = "") -> bytes:
    """Лист с заголовком, шапкой и строками. Значения пишутся как есть —
    числа остаются числами, чтобы в Excel по ним считались итоги."""
    wb = Workbook()
    ws = wb.active
    # Имя листа в Excel ограничено 31 символом и не терпит : \ / ? * [ ]
    ws.title = "".join(c for c in sheet if c not in ':\\/?*[]')[:31] or "Лист1"

    ws.append([title])
    ws["A1"].font = Font(bold=True, size=13)
    if subtitle:
        ws.append([subtitle])
        ws.cell(row=ws.max_row, column=1).font = Font(italic=True, size=10)
    ws.append([])

    head_row = ws.max_row + 1
    ws.append(headers)
    for col in range(1, len(headers) + 1):
        cell = ws.cell(row=head_row, column=col)
        cell.font = Font(bold=True)
        cell.fill = _HEAD_FILL
        cell.border = _BORDER
        cell.alignment = Alignment(vertical="center", wrap_text=True)

    for row in rows:
        ws.append(list(row))
        for col in range(1, len(headers) + 1):
            ws.cell(row=ws.max_row, column=col).border = _BORDER

    for col, header in enumerate(headers, start=1):
        longest = max([len(str(header))] + [len(str(r[col - 1])) for r in rows
                                            if col <= len(r)] or [0])
        ws.column_dimensions[get_column_letter(col)].width = min(longest + 2, MAX_WIDTH)
    # Шапка остаётся видимой при прокрутке длинной описи.
    ws.freeze_panes = ws.cell(row=head_row + 1, column=1)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


MEDIA_TYPE = ("application/vnd.openxmlformats-officedocument."
              "spreadsheetml.sheet")


def filename(stem: str) -> str:
    """Безопасное для HTTP-заголовка имя файла: только ASCII."""
    safe = "".join(c for c in stem if c.isascii() and (c.isalnum() or c in "-_")) or "export"
    return f"{safe}.xlsx"
