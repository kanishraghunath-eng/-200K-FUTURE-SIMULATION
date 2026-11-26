"""Audit a futures roll policy using contract-level CSV observations.

CSV columns: date,contract_symbol,expiry_date,close,volume,open_interest
"""
import argparse
import csv
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.futures_roll_audit import audit_contract_chain


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Contract-level CSV")
    parser.add_argument("--roll-method", choices=("calendar", "volume", "open_interest"),
                        required=True)
    parser.add_argument("--roll-days-before-expiry", type=int, default=5)
    parser.add_argument("--adjustment-method", choices=("none", "difference", "ratio"),
                        default="ratio")
    parser.add_argument("--output", default="futures_roll_audit.json")
    args = parser.parse_args()
    with Path(args.input).open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    report = audit_contract_chain(
        rows, roll_method=args.roll_method,
        roll_days_before_expiry=args.roll_days_before_expiry,
        adjustment_method=args.adjustment_method,
    )
    Path(args.output).write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    print(f"Saved report: {args.output}")
    if report["status"] != "verified":
        raise SystemExit(f"futures roll audit did not verify: {report['status']}")


if __name__ == "__main__":
    main()
