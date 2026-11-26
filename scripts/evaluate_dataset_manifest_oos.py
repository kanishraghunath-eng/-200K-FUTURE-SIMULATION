"""Per-dataset OOS diagnostics from a JSON manifest and local CSV inputs.

This runner deliberately does not download prices. Each dataset is evaluated
independently; results are not pooled into a misleading universal score.
"""
import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.dataset_manifest import DatasetManifest
from engine.canonical_data import validate_canonical_rows
from engine.providers import (CsvProvider, YahooFinanceChartProvider, StooqCsvProvider, EodhdProvider, reconcile_corporate_actions)
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
        provider = YahooFinanceChartProvider(include_ohlcv=item.get("include_ohlcv", True))
    elif provider_name == "stooq":
        provider = StooqCsvProvider()
    elif provider_name == "eodhd":
        provider = EodhdProvider()
    else:
        raise ValueError(f"unsupported provider: {provider_name}")
    try:
        fetched = provider.fetch(manifest, item.get("start"), item.get("end"))
    except Exception as exc:
        return {"instrument_id": manifest.instrument_id, "asset_class": manifest.asset_class,
                "provider": provider_name, "status": "provider_error",
                "error_type": type(exc).__name__, "error": str(exc)[:500],
                "manifest": manifest.to_dict()}
    corporate_action_audit = None
    corporate_action_payload = fetched.get("corporate_actions")
    if item.get("corporate_actions_provider") == "eodhd":
        try:
            reference_actions = corporate_action_payload
            reference_source = fetched.get("source")
            if reference_actions is None:
                reference_manifest = manifest
                reference_interval = item.get("corporate_actions_reference_interval")
                if reference_interval and reference_interval != manifest.interval:
                    reference_manifest = replace(
                        manifest, interval=reference_interval,
                        periods_per_year=252 if reference_interval == "daily" else manifest.periods_per_year,
                    )
                reference_data = YahooFinanceChartProvider(
                    include_ohlcv=False
                ).fetch(reference_manifest, item.get("actions_start", item.get("start")),
                        item.get("end"))
                reference_actions = reference_data.get("corporate_actions")
                reference_source = reference_data.get("source")
            independent_actions = EodhdProvider().fetch_corporate_actions(
                manifest, item.get("actions_start", item.get("start")),
                item.get("end"), symbol=item.get("corporate_actions_symbol")
            )
            corporate_action_audit = reconcile_corporate_actions(
                reference_actions, independent_actions
            )
            corporate_action_audit["reference_source"] = reference_source
            corporate_action_audit["reference_events_sha256"] = (
                reference_actions.get("sha256") if reference_actions else None
            )
            corporate_action_audit["independent_source_hashes"] = {
                name: value["sha256"] for name, value in independent_actions.items()
            }
            corporate_action_audit["independent_sources"] = {
                name: value["source"] for name, value in independent_actions.items()
            }
        except Exception as exc:
            corporate_action_audit = {
                "status": "unavailable",
                "error_type": type(exc).__name__,
                "error": str(exc)[:300],
                "limitations": ["Independent corporate-action source could not be retrieved."],
            }
    elif item.get("corporate_actions_applicability") == "not_applicable":
        corporate_action_audit = {
            "status": "not_applicable",
            "evidence": item.get("corporate_actions_evidence", "Instrument classification"),
        }
    audit = validate_canonical_rows(fetched["rows"], manifest,
                                    require_timezone=bool(item.get("require_timezone", False)))
    canonical_bytes = json.dumps(
        fetched["rows"], sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    source_sha256 = fetched.get("source_sha256")
    if source_sha256 is None and provider_name == "csv":
        source_sha256 = hashlib.sha256(Path(item["path"]).read_bytes()).hexdigest()
    base = {
        "instrument_id": manifest.instrument_id, "asset_class": manifest.asset_class,
        "source": fetched["source"], "provider": fetched["provider"],
        "source_sha256": source_sha256,
        "data_sha256": hashlib.sha256(canonical_bytes).hexdigest(),
        "ohlcv_included": fetched.get("ohlcv_included"),
        "provider_corporate_actions": corporate_action_payload,
        "corporate_action_audit": corporate_action_audit,
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
        prices, horizon=horizon, target_pct=float(item.get("target_pct", 0.03)),
        stop_pct=float(item.get("stop_pct", 0.02)),
        min_train=min_train, paths=paths,
        seed=int(item.get("seed", 7)),
        estimation_window=estimation_window,
        calibration_window=int(item.get("calibration_window", 252)),
        min_calibration_observations=int(item.get("min_calibration_observations", 100)),
        min_calibration_improvement=float(item.get("min_calibration_improvement", 0.0)),
        periods_per_year=manifest.effective_periods_per_year,
        step_year_fraction=float(item.get("step_year_fraction",
                                          1.0 / manifest.effective_periods_per_year)),
    )
    return dict(base, status="evaluated", observations=len(prices),
                observation_timestamps=[row["timestamp"] for row in fetched["rows"]],
                oos_diagnostic=diagnostic,
                limitations=["close-only barrier labels", "GBM assumptions",
                              "not a profitability test", "calendar and adjustment metadata require source review"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--paths", type=int, default=1000)
    parser.add_argument("--output", default="dataset_oos_report.json")
    parser.add_argument("--minimum-evaluated", type=int, default=3)
    args = parser.parse_args()
    if args.paths < 1 or args.minimum_evaluated < 1:
        parser.error("--paths and --minimum-evaluated must be positive")
    payload = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    datasets = payload.get("datasets")
    if not isinstance(datasets, list) or not datasets:
        parser.error("manifest must contain a non-empty datasets list")
    results = [evaluate_dataset(item, args.paths) for item in datasets]
    statuses = {}
    for result in results:
        statuses[result["status"]] = statuses.get(result["status"], 0) + 1
    evaluated = statuses.get("evaluated", 0)
    report = {"report_type":"per_dataset_oos_diagnostics", "paths":args.paths,
              "coverage_summary":{"dataset_count":len(results),"status_counts":statuses,
                                  "evaluated_count":evaluated,
                                  "minimum_evaluated_required":args.minimum_evaluated},
              "datasets":results}
    Path(args.output).write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False),
                                 encoding="utf-8")
    if evaluated < args.minimum_evaluated:
        raise SystemExit(f"insufficient provider coverage: {evaluated} evaluated; "
                         f"{args.minimum_evaluated} required; report saved to {args.output}")


if __name__ == "__main__":
    main()
