from decimal import Decimal

import pytest

from payroll_check import Catalog, Item, Line, Settings, reconcile
from payroll_check.engine import (
    AMOUNT_MISMATCH, DUPLICATE_LINE, EMPLOYEE_MISSING, ITEM_MISSING, MATCH, ONLY_B, SMALL_DIFFERENCE,
    UNMAPPED_CODE,
)
from payroll_check.money import fmt_money, parse_amount


def L(emp: str, code: str, amount: str, name: str = "") -> Line:
    return Line(emp, code, Decimal(amount), name)


@pytest.fixture
def catalog() -> Catalog:
    c = Catalog()
    c.add(Item("BASE", "Base salary", "earning"), "100", "0010")
    c.add(Item("TAX", "Income tax", "deduction"), "510", "9020")
    return c


def codes(result) -> list[str]:
    return [i.code for i in result.issues]


def test_identical_payrolls_match(catalog):
    r = reconcile([L("E1", "100", "2000"), L("E1", "510", "300")],
                  [L("E1", "0010", "2000"), L("E1", "9020", "300")], catalog)
    assert r.issues == []
    e = r.employees[0]
    assert (e.status, e.totals_a.gross, e.totals_a.deductions, e.totals_a.net) == ("ok", 2000, 300, 1700)
    assert all(c.status == MATCH for c in r.items)


def test_codes_are_mapped_between_systems(catalog):
    r = reconcile([L("E1", "100", "2000")], [L("E1", "0010", "2000")], catalog)
    assert [c.item.key for c in r.items] == ["BASE"]


def test_without_catalog_codes_must_match(catalog):
    r = reconcile([L("E1", "100", "2000")], [L("E1", "100", "2000")])
    assert r.issues == []


def test_amount_mismatch_is_an_error(catalog):
    r = reconcile([L("E1", "100", "2000")], [L("E1", "0010", "2100")], catalog)
    assert codes(r) == [AMOUNT_MISMATCH]
    assert r.issues[0].severity == "error"
    assert r.employees[0].net_difference == 100


def test_small_difference_is_a_warning(catalog):
    r = reconcile([L("E1", "100", "2000.00")], [L("E1", "0010", "2000.01")], catalog)
    assert codes(r) == [SMALL_DIFFERENCE]
    assert r.issues[0].severity == "warning"


def test_tolerance_hides_tiny_differences(catalog):
    r = reconcile([L("E1", "100", "2000.00")], [L("E1", "0010", "2000.01")], catalog,
                  Settings(tolerance=Decimal("0.01")))
    assert r.issues == []


def test_item_missing_on_one_side(catalog):
    r = reconcile([L("E1", "100", "2000")], [L("E1", "0010", "2000"), L("E1", "9020", "300")], catalog)
    assert codes(r) == [ITEM_MISSING]
    assert r.items[-1].status == ONLY_B


def test_employee_missing_on_one_side(catalog):
    r = reconcile([L("E1", "100", "2000"), L("E2", "100", "1500")], [L("E1", "0010", "2000")], catalog)
    assert codes(r) == [EMPLOYEE_MISSING]
    e2 = r.employees[1]
    assert (e2.status, e2.in_a, e2.in_b, e2.net_difference) == ("missing", True, False, -1500)


def test_duplicate_lines_are_summed_and_flagged(catalog):
    r = reconcile([L("E1", "100", "2000")], [L("E1", "0010", "1000"), L("E1", "0010", "1000")], catalog)
    assert codes(r) == [DUPLICATE_LINE]
    assert r.items[0].amount_b == 2000


def test_unmapped_code_is_flagged_once_and_left_out_of_totals(catalog):
    r = reconcile([L("E1", "100", "2000")], [L("E1", "0010", "2000"), L("E1", "0999", "40")], catalog)
    assert codes(r) == [UNMAPPED_CODE]
    assert r.employees[0].totals_b.gross == 2000


def test_totals_across_employees(catalog):
    r = reconcile([L("E1", "100", "1000"), L("E2", "100", "500")],
                  [L("E1", "0010", "1000"), L("E2", "0010", "600")], catalog)
    assert (r.total_net_a, r.total_net_b) == (1500, 1600)


def test_errors_are_listed_before_warnings(catalog):
    r = reconcile([L("E1", "100", "2000"), L("E2", "100", "1000")],
                  [L("E1", "0010", "2000.50"), L("E2", "0010", "1200")], catalog)
    assert [i.severity for i in r.issues] == ["error", "warning"]


@pytest.mark.parametrize("text, expected", [
    ("1234.56", "1234.56"), ("1,234.56", "1234.56"), ("1.234,56", "1234.56"), ("1234,56", "1234.56"),
    ("€ 1 234,50", "1234.50"), ("-12.5", "-12.50"), ("1.234.567", "1234567.00"), ("1,234,567", "1234567.00"),
    ("0,005", "0.01"),
])
def test_parse_amount(text, expected):
    assert parse_amount(text) == Decimal(expected)


@pytest.mark.parametrize("text", ["", "abc", "-", "€"])
def test_parse_amount_rejects_garbage(text):
    with pytest.raises(ValueError):
        parse_amount(text)


def test_fmt_money():
    assert fmt_money(Decimal("1234.5")) == "€1,234.50"
    assert fmt_money(Decimal("-27"), signed=True) == "-€27.00"
    assert fmt_money(Decimal("150"), signed=True) == "+€150.00"
    assert fmt_money(None) == "—"
