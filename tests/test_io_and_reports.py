import pytest
from openpyxl import load_workbook

from payroll_check import reconcile
from payroll_check.cli import main
from payroll_check.engine import AMOUNT_MISMATCH, DUPLICATE_LINE, EMPLOYEE_MISSING, ITEM_MISSING, SMALL_DIFFERENCE, UNMAPPED_CODE
from payroll_check.io import load_catalog, load_lines
from payroll_check.report_excel import write_excel
from payroll_check.report_html import render_html
from payroll_check.sample import generate


@pytest.fixture
def sample(tmp_path):
    return generate(tmp_path / "data")


@pytest.fixture
def result(sample):
    return reconcile(load_lines(sample["hr"]), load_lines(sample["provider"]), load_catalog(sample["items"]))


def test_sample_finds_every_planted_problem(result):
    found = {(i.employee_id, i.code) for i in result.issues}
    assert found == {
        ("E002", SMALL_DIFFERENCE), ("E004", AMOUNT_MISMATCH), ("E005", UNMAPPED_CODE), ("E007", ITEM_MISSING),
        ("E009", AMOUNT_MISMATCH), ("E009", DUPLICATE_LINE), ("E011", EMPLOYEE_MISSING), ("E012", EMPLOYEE_MISSING),
    }


def test_clean_employees_match(result):
    ok = {e.employee_id for e in result.employees if e.status == "ok"}
    assert ok == {"E001", "E003", "E006", "E008", "E010"}


def test_provider_file_with_european_format_is_read(sample):
    lines = load_lines(sample["provider"])
    base = next(l for l in lines if l.employee_id == "E001" and l.code == "0010")
    assert str(base.amount) == "1850.00" and base.employee_name == "Ana Ribeiro"


def test_excel_input_is_supported(tmp_path, sample):
    import pandas as pd
    xlsx = tmp_path / "hr.xlsx"
    pd.read_csv(sample["hr"], dtype=str).to_excel(xlsx, index=False)
    assert load_lines(xlsx) == load_lines(sample["hr"])


def test_missing_columns_are_reported(tmp_path):
    path = tmp_path / "x.csv"
    path.write_text("employee_id,amount\nE1,10\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing column"):
        load_lines(path)


def test_bad_amount_reports_row(tmp_path):
    path = tmp_path / "x.csv"
    path.write_text("employee_id,item_code,amount\nE1,100,10\nE1,110,abc\n", encoding="utf-8")
    with pytest.raises(ValueError, match="row 3"):
        load_lines(path)


def test_catalog_rejects_unknown_type(tmp_path):
    path = tmp_path / "items.csv"
    path.write_text("key,name,type,code_a,code_b\nX,Thing,bonus,1,2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="earning"):
        load_catalog(path)


def test_excel_report_sheets(tmp_path, result):
    wb = load_workbook(write_excel(result, tmp_path / "r.xlsx"))
    assert wb.sheetnames == ["Summary", "Issues", "Items"]
    assert wb["Issues"].max_row == 1 + len(result.issues)
    assert wb["Items"].max_row == 1 + len(result.items)


def test_html_escapes_names():
    from decimal import Decimal
    from payroll_check import Line
    html = render_html(reconcile([Line("E1", "1", Decimal(1), "<b>x</b>")], []))
    assert "<b>x</b>" not in html and "&lt;b&gt;x&lt;/b&gt;" in html


def test_cli_end_to_end(tmp_path, capsys):
    data, out = tmp_path / "data", tmp_path / "out"
    assert main(["sample", "--out", str(data)]) == 0
    args = ["compare", "--a", str(data / "hr_system.csv"), "--b", str(data / "payroll_provider.csv"),
            "--items", str(data / "items.csv"), "--period", "2026-10", "--out", str(out)]
    assert main(args) == 0
    assert (out / "payroll_reconciliation_2026-10.xlsx").exists()
    assert "5 error(s), 3 warning(s)" in capsys.readouterr().out
    assert main(args + ["--strict"]) == 1


def test_cli_friendly_error(tmp_path, capsys):
    assert main(["compare", "--a", str(tmp_path / "no.csv"), "--b", str(tmp_path / "no.csv")]) == 2
    assert "File not found" in capsys.readouterr().err
