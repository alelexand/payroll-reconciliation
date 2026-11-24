"""Money helpers. Amounts are always Decimal, never float, so cents never drift."""

from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

CENT = Decimal("0.01")


def to_money(value: Decimal | int | str) -> Decimal:
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def parse_amount(text: object) -> Decimal:
    """Parse amounts written in English or European style.

    "1,234.56", "1.234,56", "1234,56", "€ 1 234.56" and "-12.5" are all accepted.
    The last "," or "." is taken as the decimal separator when both appear.
    """
    raw = str(text).strip()
    cleaned = re.sub(r"[^\d,.\-+]", "", raw)
    if not re.search(r"\d", cleaned):
        raise ValueError(f"invalid amount {raw!r}")
    if "," in cleaned and "." in cleaned:
        decimal_sep = "," if cleaned.rfind(",") > cleaned.rfind(".") else "."
        thousands = "." if decimal_sep == "," else ","
        cleaned = cleaned.replace(thousands, "").replace(decimal_sep, ".")
    elif "," in cleaned:
        parts = cleaned.split(",")
        # "1,234" with exactly three digits after a single comma is ambiguous; treat it as thousands
        # only when there is more than one comma ("1,234,567"). Otherwise the comma is decimal.
        cleaned = cleaned.replace(",", "") if len(parts) > 2 else cleaned.replace(",", ".")
    elif cleaned.count(".") > 1:
        cleaned = cleaned.replace(".", "")
    try:
        return to_money(cleaned)
    except InvalidOperation:
        raise ValueError(f"invalid amount {raw!r}") from None


def fmt_money(value: Decimal | None, symbol: str = "€", signed: bool = False) -> str:
    if value is None:
        return "—"
    sign = "-" if value < 0 else ("+" if signed and value > 0 else "")
    return f"{sign}{symbol}{abs(value):,.2f}"
