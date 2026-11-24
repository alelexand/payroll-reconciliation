"""Compares two payroll exports line by line, employee by employee.

Typical use: the company's HR system on one side and the payroll provider or
accounting firm on the other. Both describe the same month; this finds where they disagree.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Iterable

from .money import to_money

EARNING, DEDUCTION = "earning", "deduction"
ERROR, WARNING = "error", "warning"

EMPLOYEE_MISSING = "EMPLOYEE_MISSING"
ITEM_MISSING = "ITEM_MISSING"
AMOUNT_MISMATCH = "AMOUNT_MISMATCH"
SMALL_DIFFERENCE = "SMALL_DIFFERENCE"
DUPLICATE_LINE = "DUPLICATE_LINE"
UNMAPPED_CODE = "UNMAPPED_CODE"

SEVERITY = {
    EMPLOYEE_MISSING: ERROR,
    ITEM_MISSING: ERROR,
    AMOUNT_MISMATCH: ERROR,
    SMALL_DIFFERENCE: WARNING,
    DUPLICATE_LINE: WARNING,
    UNMAPPED_CODE: WARNING,
}

MATCH, MISMATCH, ONLY_A, ONLY_B = "match", "mismatch", "only_a", "only_b"


@dataclass(frozen=True)
class Item:
    key: str
    name: str
    kind: str | None  # EARNING, DEDUCTION, or None when unknown


@dataclass(frozen=True)
class Line:
    employee_id: str
    code: str
    amount: Decimal
    employee_name: str = ""


@dataclass
class Catalog:
    """Maps each side's own item codes to one shared item, e.g. "120" and "0200" -> OVERTIME."""

    items: dict[str, Item] = field(default_factory=dict)
    code_a: dict[str, str] = field(default_factory=dict)
    code_b: dict[str, str] = field(default_factory=dict)

    def add(self, item: Item, code_a: str | None, code_b: str | None) -> None:
        self.items[item.key] = item
        if code_a:
            self.code_a[code_a] = item.key
        if code_b:
            self.code_b[code_b] = item.key

    def resolve(self, side: str, code: str) -> Item | None:
        key = (self.code_a if side == "a" else self.code_b).get(code)
        return self.items[key] if key else None


@dataclass(frozen=True)
class Settings:
    label_a: str = "HR system"
    label_b: str = "Payroll provider"
    tolerance: Decimal = Decimal("0.00")
    """Differences up to this value are considered a match."""
    small_difference: Decimal = Decimal("1.00")
    """Differences up to this value are warnings (often rounding); above it they are errors."""


@dataclass(frozen=True)
class Issue:
    employee_id: str
    employee_name: str
    code: str
    message: str
    item: str = ""

    @property
    def severity(self) -> str:
        return SEVERITY[self.code]


@dataclass
class ItemComparison:
    employee_id: str
    item: Item
    amount_a: Decimal | None
    amount_b: Decimal | None
    status: str

    @property
    def difference(self) -> Decimal:
        return (self.amount_b or Decimal(0)) - (self.amount_a or Decimal(0))


@dataclass
class Totals:
    gross: Decimal = Decimal("0.00")
    deductions: Decimal = Decimal("0.00")

    @property
    def net(self) -> Decimal:
        return self.gross - self.deductions


@dataclass
class EmployeeComparison:
    employee_id: str
    name: str
    in_a: bool
    in_b: bool
    totals_a: Totals
    totals_b: Totals
    issues: int

    @property
    def net_difference(self) -> Decimal:
        return self.totals_b.net - self.totals_a.net

    @property
    def status(self) -> str:
        if not (self.in_a and self.in_b):
            return "missing"
        return "ok" if self.issues == 0 else "review"


@dataclass
class Reconciliation:
    settings: Settings
    employees: list[EmployeeComparison]
    items: list[ItemComparison]
    issues: list[Issue]

    @property
    def total_net_a(self) -> Decimal:
        return sum((e.totals_a.net for e in self.employees), Decimal("0.00"))

    @property
    def total_net_b(self) -> Decimal:
        return sum((e.totals_b.net for e in self.employees), Decimal("0.00"))

    def count(self, severity: str) -> int:
        return sum(1 for i in self.issues if i.severity == severity)


def _aggregate(side: str, lines: Iterable[Line], catalog: Catalog, settings: Settings,
               issues: list[Issue]) -> tuple[dict[str, dict[str, Decimal]], dict[str, str], dict[str, Item]]:
    label = settings.label_a if side == "a" else settings.label_b
    amounts: dict[str, dict[str, Decimal]] = defaultdict(lambda: defaultdict(lambda: Decimal("0.00")))
    seen: dict[tuple[str, str], int] = defaultdict(int)
    names: dict[str, str] = {}
    items: dict[str, Item] = {}
    unmapped: set[tuple[str, str]] = set()

    for line in lines:
        item = catalog.resolve(side, line.code)
        if item is None:
            item = Item(key=line.code, name=f"Code {line.code}", kind=None)
            if catalog.items and (line.employee_id, line.code) not in unmapped:
                unmapped.add((line.employee_id, line.code))
                issues.append(Issue(line.employee_id, line.employee_name, UNMAPPED_CODE,
                                    f"Code {line.code} in {label} is not in the item mapping; "
                                    "left out of gross and net", item.name))
        items[item.key] = item
        if line.employee_name:
            names.setdefault(line.employee_id, line.employee_name)
        seen[(line.employee_id, item.key)] += 1
        amounts[line.employee_id][item.key] += to_money(line.amount)

    for (employee_id, key), count in seen.items():
        if count > 1:
            issues.append(Issue(employee_id, names.get(employee_id, ""), DUPLICATE_LINE,
                                f"{count} lines for the same item in {label}; amounts were added up",
                                items[key].name))
    return amounts, names, items


def reconcile(lines_a: Iterable[Line], lines_b: Iterable[Line], catalog: Catalog | None = None,
              settings: Settings | None = None) -> Reconciliation:
    catalog = catalog or Catalog()
    settings = settings or Settings()
    issues: list[Issue] = []

    amounts_a, names_a, items_a = _aggregate("a", lines_a, catalog, settings, issues)
    amounts_b, names_b, items_b = _aggregate("b", lines_b, catalog, settings, issues)
    known_items = {**items_a, **items_b}
    # With a mapping in place, an unmapped code already raised UNMAPPED_CODE; don't report it twice.
    unmapped = {k for k, item in known_items.items() if item.kind is None} if catalog.items else set()

    employees: list[EmployeeComparison] = []
    comparisons: list[ItemComparison] = []
    for employee_id in sorted(set(amounts_a) | set(amounts_b)):
        name = names_a.get(employee_id) or names_b.get(employee_id) or ""
        a, b = amounts_a.get(employee_id), amounts_b.get(employee_id)

        if a is None or b is None:
            present, absent = (settings.label_a, settings.label_b) if b is None else (settings.label_b, settings.label_a)
            issues.append(Issue(employee_id, name, EMPLOYEE_MISSING, f"Paid in {present} but missing from {absent}"))

        for key in sorted(set(a or {}) | set(b or {}), key=lambda k: known_items[k].name):
            item = known_items[key]
            va = a.get(key) if a is not None else None
            vb = b.get(key) if b is not None else None
            if a is not None and b is not None and (va is None or vb is None):
                status = ONLY_A if vb is None else ONLY_B
                where, missing_in = (settings.label_a, settings.label_b) if status == ONLY_A else (settings.label_b, settings.label_a)
                value = va if status == ONLY_A else vb
                if key not in unmapped:
                    issues.append(Issue(employee_id, name, ITEM_MISSING,
                                        f"{item.name} of {value:,.2f} in {where} is missing from {missing_in}",
                                        item.name))
            elif va is not None and vb is not None:
                diff = abs(vb - va)
                if diff <= settings.tolerance:
                    status = MATCH
                else:
                    status = MISMATCH
                    code = SMALL_DIFFERENCE if diff <= settings.small_difference else AMOUNT_MISMATCH
                    issues.append(Issue(employee_id, name, code,
                                        f"{item.name}: {va:,.2f} in {settings.label_a} vs {vb:,.2f} in "
                                        f"{settings.label_b} (difference {vb - va:+,.2f})", item.name))
            else:
                status = ONLY_A if vb is None else ONLY_B
            comparisons.append(ItemComparison(employee_id, item, va, vb, status))

        employees.append(EmployeeComparison(
            employee_id=employee_id,
            name=name,
            in_a=a is not None,
            in_b=b is not None,
            totals_a=_totals(a or {}, known_items),
            totals_b=_totals(b or {}, known_items),
            # Duplicate/unmapped issues were added up front for everyone; the rest just now.
            issues=sum(1 for i in issues if i.employee_id == employee_id),
        ))

    order = {ERROR: 0, WARNING: 1}
    issues.sort(key=lambda i: (order[i.severity], i.employee_id, i.item))
    return Reconciliation(settings, employees, comparisons, issues)


def _totals(amounts: dict[str, Decimal], items: dict[str, Item]) -> Totals:
    totals = Totals()
    for key, value in amounts.items():
        kind = items[key].kind
        if kind == EARNING:
            totals.gross += value
        elif kind == DEDUCTION:
            totals.deductions += value
    return totals
