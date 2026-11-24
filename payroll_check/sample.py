"""Builds a fictional month of payroll from two systems that almost agree.

Side A is the company's HR system (comma-separated, amounts like 1234.56). Side B is the
payroll provider (semicolon-separated, different column names and item codes, amounts like
1.234,56), as often happens in real life. A handful of discrepancies are planted on purpose.
All names and amounts are invented.
"""

from __future__ import annotations

import csv
from decimal import Decimal
from pathlib import Path

from .money import to_money

# key, name, type, code in A, code in B
ITEMS = [
    ("BASE", "Base salary", "earning", "100", "0010"),
    ("OVERTIME", "Overtime", "earning", "120", "0200"),
    ("NIGHT", "Night shift allowance", "earning", "130", "0250"),
    ("BONUS", "Performance bonus", "earning", "140", "0400"),
    ("MEAL", "Meal allowance", "earning", "210", "0310"),
    ("SOCIAL", "Social security (employee)", "deduction", "500", "9010"),
    ("TAX", "Income tax withholding", "deduction", "510", "9020"),
    ("UNION", "Union fee", "deduction", "520", "9030"),
]

# id, name, base salary, overtime, night, bonus, union member
EMPLOYEES = [
    ("E001", "Ana Ribeiro", "1850.00", "0", "0", "0", True),
    ("E002", "Bruno Costa", "2100.00", "87.45", "0", "0", False),
    ("E003", "Clara Dubois", "2650.00", "0", "0", "300.00", False),
    ("E004", "Daniel Weber", "1980.00", "152.40", "64.00", "0", True),
    ("E005", "Elena Rossi", "1720.00", "0", "0", "0", False),
    ("E006", "Filipe Santos", "2300.00", "45.10", "128.00", "0", True),
    ("E007", "Greta Novak", "1650.00", "0", "0", "0", False),
    ("E008", "Hugo Martins", "3100.00", "0", "0", "450.00", False),
    ("E009", "Inês Carvalho", "2450.00", "0", "0", "150.00", True),
    ("E010", "Jonas Becker", "1900.00", "112.80", "0", "0", False),
    ("E011", "Katarina Horvat", "2000.00", "0", "0", "0", False),
    ("E012", "Luca Bianchi", "2750.00", "0", "96.00", "0", True),
]
MEAL_ALLOWANCE = Decimal("132.00")  # 22 days x 6.00
SOCIAL_RATE = Decimal("0.11")


def _tax_rate(taxable: Decimal) -> Decimal:
    if taxable < 2000:
        return Decimal("0.09")
    if taxable < 3000:
        return Decimal("0.15")
    return Decimal("0.21")


def _payslip(base: str, overtime: str, night: str, bonus: str, union: bool) -> dict[str, Decimal]:
    lines = {"BASE": to_money(base), "MEAL": MEAL_ALLOWANCE}
    for key, value in (("OVERTIME", overtime), ("NIGHT", night), ("BONUS", bonus)):
        if Decimal(value):
            lines[key] = to_money(value)
    taxable = sum(v for k, v in lines.items() if k != "MEAL")
    lines["SOCIAL"] = to_money(taxable * SOCIAL_RATE)
    lines["TAX"] = to_money(taxable * _tax_rate(taxable))
    if union:
        lines["UNION"] = to_money(lines["BASE"] * Decimal("0.01"))
    return lines


def build() -> tuple[list[tuple[str, str, str, Decimal]], list[tuple[str, str, str, Decimal]]]:
    code_a = {k: a for k, _, _, a, _ in ITEMS}
    code_b = {k: b for k, _, _, _, b in ITEMS}
    side_a, side_b = [], []
    for emp_id, name, *pay, union in EMPLOYEES:
        slip = _payslip(*pay, union)
        if emp_id != "E012":  # Luca left last month; only the provider still pays him
            side_a += [(emp_id, name, code_a[k], v) for k, v in slip.items()]
        if emp_id == "E011":  # Katarina joined this month; the provider was never told
            continue
        b = dict(slip)
        if emp_id == "E002":
            b["SOCIAL"] += Decimal("0.01")              # provider rounds differently
        if emp_id == "E004":
            b["OVERTIME"] = Decimal("125.40")           # digits swapped when typed in
        if emp_id == "E007":
            del b["MEAL"]                               # allowance forgotten
        rows = [(emp_id, name, code_b[k], v) for k, v in b.items()]
        if emp_id == "E009":
            rows.append((emp_id, name, code_b["BONUS"], b["BONUS"]))  # bonus entered twice
        if emp_id == "E005":
            rows.append((emp_id, name, "0999", Decimal("40.00")))     # code nobody mapped
        side_b += rows
    return side_a, side_b


def _european(value: Decimal) -> str:
    return f"{value:,.2f}".replace(",", " ").replace(".", ",").replace(" ", ".")


def generate(out_dir: str | Path) -> dict[str, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    side_a, side_b = build()
    paths = {"hr": out / "hr_system.csv", "provider": out / "payroll_provider.csv", "items": out / "items.csv"}

    with paths["hr"].open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["employee_id", "employee_name", "item_code", "amount"])
        w.writerows((e, n, c, f"{v:.2f}") for e, n, c, v in side_a)
    with paths["provider"].open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["Worker ID", "Name", "Wage type", "Value"])
        w.writerows((e, n, c, _european(v)) for e, n, c, v in side_b)
    with paths["items"].open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["key", "name", "type", "code_a", "code_b"])
        w.writerows(ITEMS)
    return paths
