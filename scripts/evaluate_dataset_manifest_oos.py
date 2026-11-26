"""Per-dataset OOS diagnostics from a JSON manifest and local CSV inputs.

This runner deliberately does not download prices. Each dataset is evaluated
independently; results are not pooled into a misleading universal score.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.dataset_manifest import DatasetManifest
from engine.canonical_data import validate_canonical_rows
from engine.providers import CsvProvider, YahooFinanceChartProvider, StooqCsvProvider
from engine.backtest import walk_forward_barrier_diagnostic


def evaluate_dataset(item, paths=1000):
    metadata_fields = {key: item[key] for key in (
        "instrument_id", "asset_class", "source", "currency", "interval")}
    optional = ("price_field", "timezone", "calendar", "adjustment_basis",
                "corporate_actions_reviewed", "futures_roll_method", "notes", "periods_per_year")
    metadata_fields.update({key: item[key] for key in optional if key in item})
    manifest = DatasetManifest(**metadata_fields)
    manifest.validate()
    provider_name = item.get("provider", "csv")
    if provider_name == "csv":
        provider = CsvProvider(item["path"], item.get("timestamp_column", "date"),
                               item.get("close_column", "close"))
    elif provider_name == "yahoo":
        provider = YahooFinanceChartProvider()
    elif provider_name == "stooq":
        provider = StooqCsvProvider()
    else:
        raise ValueError(f"unsupported provider: {provider_name}")
    fetched = provider.fetch(manifest, item.get("start"), item.get("end"))
    audit = validate_canonical_rows(fetched["rows"], manifest,
                                    require_timezone=bool(item.get("require_timezone", False)))
    if provider_name == "csv":
        raw = Path(item["path"]).read_bytes()
    else:
        raw = json.dumps(fetched["rows"], sort_keys=True, separators=(",", ":")).encode("utf-8")
    base = {
        "instrument_id": manifest.instrument_id, "asset_class": manifest.asset_class,
        "source": fetched["source"], "provider": fetched["provider"],
        "data_sha256": hashlib.sha256(raw).hexdigest(),
        "manifest": manifest.to_dict(), "audit": audit,
    }
    if not audit["valid"]:
        return dict(base, status="rejected")
    prices = [float(row["close"]) for row in fetched["rows"]]
    horizon = int(item.get("horizon", 5))
    min_train = int(item.get("min_train", 60))
    estimation_window = int(item.get("estimation_window", 252))
    required = max(min_train, estimation_window) + horizon + 1
    if len(prices) < max(required, 70):
        return dict(base, status="insufficient_data", observations=len(prices),
                    required_observations=max(required, 70))
    diagnostic = walk_forward_barrier_diagnostic(
        prices, horizon=horizon, min_train=min_train, paths=paths,
        estimation_window=estimation_window,
        periods_per_year=manifest.effective_periods_per_year,
        step_year_fraction=float(item.get("step_year_fraction",
                                          1.0 / manifest.effective_periods_per_year)),
    )
    return dict(base, status="evaluated", observations=len(prices),
                oos_diagnostic=diagnostic,
                limitations=["close-only barrier labels", "GBM assumptions",
                              "not a profitability test", "calendar and adjustment metadata require source review"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--paths", type=int, default=1000)
    parser.add_argument("--output", default="dataset_oos_report.json")
    args = parser.parse_args()
    if args.paths < 1:
        parser.error("--paths must be positive")
    payload = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    datasets = payload.get("datasets")
    if not isinstance(datasets, list) or not datasets:
        parser.error("manifest must contain a non-empty datasets list")
    report = {"report_type":"per_dataset_oos_diagnostics", "paths":args.paths,
              "datasets":[evaluate_dataset(item, args.paths) for item in datasets]}
    Path(args.output).write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False),
                                 encoding="utf-8")


if __name__ == "__main__":
    main()
