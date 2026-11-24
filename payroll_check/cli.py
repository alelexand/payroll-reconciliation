"""Command line: `python -m payroll_check sample` and `python -m payroll_check compare ...`."""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .engine import ERROR, WARNING, Settings, reconcile
from .io import load_catalog, load_lines
from .money import fmt_money
from .report_excel import write_excel
from .report_html import write_html
from .sample import generate


def _decimal(text: str) -> Decimal:
    try:
        return Decimal(text.replace(",", "."))
    except InvalidOperation:
        raise argparse.ArgumentTypeError(f"invalid amount {text!r}") from None


def cmd_sample(args: argparse.Namespace) -> int:
    for kind, path in generate(args.out).items():
        print(f"  {kind:<9} {path}")
    print(f"\nNext: python -m payroll_check compare --a {args.out}/hr_system.csv "
          f"--b {args.out}/payroll_provider.csv --items {args.out}/items.csv")
    return 0


def cmd_compare(args: argparse.Namespace) -> int:
    settings = Settings(label_a=args.label_a, label_b=args.label_b,
                        tolerance=args.tolerance, small_difference=args.small_difference)
    result = reconcile(load_lines(args.a), load_lines(args.b), load_catalog(args.items), settings)

    out = Path(args.out)
    stem = f"payroll_reconciliation{'_' + args.period if args.period else ''}"
    excel = write_excel(result, out / f"{stem}.xlsx")
    html = write_html(result, out / f"{stem}.html", args.period)

    print(f"\n  {'Employee':<18}{'Status':<10}{'Net ' + settings.label_a[:9]:>16}{'Net ' + settings.label_b[:9]:>16}{'Difference':>13}")
    for e in result.employees:
        net_a = fmt_money(e.totals_a.net) if e.in_a else "-"
        net_b = fmt_money(e.totals_b.net) if e.in_b else "-"
        diff = fmt_money(e.net_difference, signed=True) if e.net_difference else ""
        print(f"  {e.name[:17]:<18}{e.status:<10}{net_a:>16}{net_b:>16}{diff:>13}")
    print(f"\n  {result.count(ERROR)} error(s), {result.count(WARNING)} warning(s)")
    print(f"  Net {settings.label_a}: {fmt_money(result.total_net_a)} · Net {settings.label_b}: "
          f"{fmt_money(result.total_net_b)} · difference {fmt_money(result.total_net_b - result.total_net_a, signed=True)}")
    print(f"\n  Excel: {excel}\n  HTML:  {html}")
    return 1 if args.strict and result.count(ERROR) else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="payroll_check",
                                     description="Compare two payroll exports and list every discrepancy.")
    sub = parser.add_subparsers(dest="command", required=True)

    s = sub.add_parser("sample", help="generate fictional payroll data from two systems")
    s.add_argument("--out", default="sample_data")
    s.set_defaults(func=cmd_sample)

    c = sub.add_parser("compare", help="compare two payroll files")
    c.add_argument("--a", required=True, type=Path, help="first export (.csv or .xlsx)")
    c.add_argument("--b", required=True, type=Path, help="second export (.csv or .xlsx)")
    c.add_argument("--items", type=Path, help="item mapping (.csv or .xlsx); without it codes must match exactly")
    c.add_argument("--label-a", default="HR system")
    c.add_argument("--label-b", default="Payroll provider")
    c.add_argument("--period", default="", help="label for the report, e.g. 2026-10")
    c.add_argument("--tolerance", type=_decimal, default=Decimal("0.00"), help="differences up to this are ignored")
    c.add_argument("--small-difference", type=_decimal, default=Decimal("1.00"),
                   help="differences up to this are warnings instead of errors")
    c.add_argument("--out", default="reports")
    c.add_argument("--strict", action="store_true", help="exit with code 1 when there are errors")
    c.set_defaults(func=cmd_compare)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
