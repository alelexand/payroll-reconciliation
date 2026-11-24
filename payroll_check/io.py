"""Reading payroll exports and the item mapping from CSV or Excel."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .engine import DEDUCTION, EARNING, Catalog, Item, Line
from .money import parse_amount

ALIASES = {
    "employee_id": {"employee_id", "employee", "emp_id", "id", "employee_number", "worker_id"},
    "employee_name": {"employee_name", "name", "full_name"},
    "item_code": {"item_code", "code", "pay_code", "item", "wage_type"},
    "amount": {"amount", "value", "total"},
}


def _read_table(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        df = pd.read_excel(path, dtype=str)
    elif suffix == ".csv":
        df = pd.read_csv(path, dtype=str, sep=None, engine="python", encoding="utf-8-sig")
    else:
        raise ValueError(f"Unsupported file type: {path.suffix} (use .csv or .xlsx)")
    df.columns = [str(c).strip().lower().replace(" ", "_").replace("-", "_") for c in df.columns]
    return df.dropna(how="all")


def _normalise_columns(df: pd.DataFrame, path: str | Path) -> pd.DataFrame:
    rename = {}
    for canonical, options in ALIASES.items():
        match = next((c for c in df.columns if c in options), None)
        if match:
            rename[match] = canonical
    df = df.rename(columns=rename)
    missing = {"employee_id", "item_code", "amount"} - set(df.columns)
    if missing:
        raise ValueError(f"{Path(path).name}: missing column(s) {', '.join(sorted(missing))}")
    return df


def load_lines(path: str | Path) -> list[Line]:
    df = _normalise_columns(_read_table(path), path)
    lines = []
    for i, row in enumerate(df.to_dict("records"), start=2):
        try:
            amount = parse_amount(row["amount"])
        except ValueError as exc:
            raise ValueError(f"{Path(path).name}, row {i}: {exc}") from None
        name = row.get("employee_name")
        lines.append(Line(
            employee_id=str(row["employee_id"]).strip(),
            code=str(row["item_code"]).strip(),
            amount=amount,
            employee_name="" if name is None or pd.isna(name) else str(name).strip(),
        ))
    return lines


def load_catalog(path: str | Path | None) -> Catalog:
    catalog = Catalog()
    if path is None:
        return catalog
    df = _read_table(path)
    missing = {"key", "name", "type", "code_a", "code_b"} - set(df.columns)
    if missing:
        raise ValueError(f"{Path(path).name}: missing column(s) {', '.join(sorted(missing))}")
    for i, row in enumerate(df.to_dict("records"), start=2):
        kind = str(row["type"]).strip().lower()
        if kind not in {EARNING, DEDUCTION}:
            raise ValueError(f"{Path(path).name}, row {i}: type must be 'earning' or 'deduction', got {row['type']!r}")
        code = lambda v: None if v is None or pd.isna(v) or not str(v).strip() else str(v).strip()  # noqa: E731
        catalog.add(Item(str(row["key"]).strip(), str(row["name"]).strip(), kind), code(row["code_a"]), code(row["code_b"]))
    return catalog
