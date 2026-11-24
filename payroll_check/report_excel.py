"""Excel report with Summary, Issues and Items sheets."""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from .engine import ERROR, MATCH, WARNING, Reconciliation

HEADER_FILL = PatternFill("solid", fgColor="1E3A8A")
HEADER_FONT = Font(bold=True, color="FFFFFF")
FILLS = {
    ERROR: PatternFill("solid", fgColor="FDE2E1"),
    WARNING: PatternFill("solid", fgColor="FEF3C7"),
    "ok": PatternFill("solid", fgColor="DCFCE7"),
}
MONEY = '#,##0.00;[Red]-#,##0.00;"-"'
STATUS_TEXT = {"ok": "OK", "review": "Review", "missing": "Missing on one side"}


def _sheet(ws: Worksheet, headers: list[str], rows: list[list], widths: list[int]) -> None:
    ws.append(headers)
    for cell in ws[1]:
        cell.fill, cell.font = HEADER_FILL, HEADER_FONT
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    for row in rows:
        ws.append(row)
    for i, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = width
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions


def write_excel(result: Reconciliation, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    a, b = result.settings.label_a, result.settings.label_b
    names = {e.employee_id: e.name for e in result.employees}
    wb = Workbook()

    summary = wb.active
    summary.title = "Summary"
    _sheet(summary,
           ["Employee ID", "Name", "Status", f"Gross ({a})", f"Gross ({b})", f"Deductions ({a})",
            f"Deductions ({b})", f"Net ({a})", f"Net ({b})", "Net difference", "Issues"],
           [[e.employee_id, e.name, STATUS_TEXT[e.status],
             e.totals_a.gross if e.in_a else None, e.totals_b.gross if e.in_b else None,
             e.totals_a.deductions if e.in_a else None, e.totals_b.deductions if e.in_b else None,
             e.totals_a.net if e.in_a else None, e.totals_b.net if e.in_b else None,
             e.net_difference, e.issues]
            for e in result.employees],
           [12, 20, 20, 15, 15, 15, 15, 15, 15, 15, 8])
    for row in summary.iter_rows(min_row=2):
        for cell in row[3:10]:
            cell.number_format = MONEY
        row[2].fill = FILLS["ok"] if row[2].value == "OK" else FILLS[ERROR if row[2].value != "Review" else WARNING]
    total_row = summary.max_row + 2
    summary.cell(total_row, 2, "Total net").font = Font(bold=True)
    for col, value in ((8, result.total_net_a), (9, result.total_net_b), (10, result.total_net_b - result.total_net_a)):
        cell = summary.cell(total_row, col, value)
        cell.number_format, cell.font = MONEY, Font(bold=True)

    issues = wb.create_sheet("Issues")
    _sheet(issues, ["Severity", "Employee ID", "Name", "Item", "Issue", "Details"],
           [[i.severity.upper(), i.employee_id, i.employee_name or names.get(i.employee_id, ""), i.item, i.code, i.message]
            for i in result.issues],
           [10, 12, 20, 26, 20, 90])
    for row in issues.iter_rows(min_row=2):
        for cell in row:
            cell.fill = FILLS[row[0].value.lower()]

    items = wb.create_sheet("Items")
    _sheet(items, ["Employee ID", "Name", "Item", "Type", a, b, "Difference", "Status"],
           [[c.employee_id, names.get(c.employee_id, ""), c.item.name, c.item.kind or "unmapped",
             c.amount_a, c.amount_b, c.difference, c.status]
            for c in result.items],
           [12, 20, 28, 11, 15, 15, 13, 10])
    for row in items.iter_rows(min_row=2):
        for cell in row[4:7]:
            cell.number_format = MONEY
        if row[7].value != MATCH:
            row[7].fill = FILLS[ERROR]

    wb.save(path)
    return path
