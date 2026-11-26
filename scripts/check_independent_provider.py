"""Quick live check of the optional Yahoo/EODHD independent data comparison."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.evaluate_multi_market_oos import fetch_adjusted_close, cross_provider_check


def main():
    raw, rows, yahoo_url = fetch_adjusted_close("VTI")
    result = cross_provider_check(rows, symbol="VTI")
    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "instrument": "VTI.US",
        "reference_provider": "Yahoo Finance adjusted close",
        "comparison_provider": "EODHD adjusted close",
        "yahoo_observations": len(rows),
        "yahoo_data_sha256": hashlib.sha256(raw).hexdigest(),
        "yahoo_source_url": yahoo_url,
        "result": result,
        "interpretation": "Vendor consistency check only; not market forecast validation.",
    }
    Path("provider_crosscheck_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()