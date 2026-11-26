"""Run the pre-registered, untouched future-holdout OOS evaluation.

This command intentionally returns an awaiting/blocked report until every
pre-registered candidate meets its data and minimum-sample gates.
"""
import argparse
from datetime import date
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.analyze_manifest_oos_uncertainty import block_bootstrap_skill_interval
from scripts.evaluate_dataset_manifest_oos import evaluate_dataset
from engine.backtest import walk_forward_barrier_diagnostic


def _holm_adjust(results):
    tests = [
        (float(item["bootstrap"]["one_sided_bootstrap_p_value"]), index)
        for index, item in enumerate(results)
        if item.get("bootstrap", {}).get("one_sided_bootstrap_p_value") is not None
    ]
    tests.sort(key=lambda pair: pair[0])
    family_size = len(tests)
    running_max = 0.0
    for rank, (p_value, index) in enumerate(tests):
        adjusted = min(1.0, (family_size - rank) * p_value)
        running_max = max(running_max, adjusted)
        results[index]["holm_adjusted_p_value"] = running_max
        results[index]["holm_family_size"] = family_size
    return results


def _metadata_blockers(item, evaluated):
    blockers = []
    if evaluated.get("status") != "data_validated":
        blockers.append("dataset_status:" + str(evaluated.get("status")))
        return blockers
    if not evaluated.get("source_sha256") or not evaluated.get("data_sha256"):
        blockers.append("missing_source_or_canonical_hash")
    audit = evaluated.get("audit", {})
    if not audit.get("valid"):
        blockers.append("canonical_data_audit_failed")
    if not item.get("timezone") or not item.get("calendar"):
        blockers.append("timezone_or_calendar_not_declared")
    if item.get("adjustment_basis", "unknown") == "unknown":
        blockers.append("price_adjustment_basis_unknown")
    applicability = item.get("corporate_actions_applicability")
    if applicability == "not_applicable":
        pass
    elif item.get("corporate_actions_provider"):
        action_status = evaluated.get("corporate_action_audit", {}).get("status")
        if action_status != "matched":
            blockers.append("corporate_action_reconciliation:" + str(action_status))
    else:
        blockers.append("corporate_action_status_not_verified")
    if item.get("asset_class") == "commodity_future":
        roll_status = evaluated.get("futures_roll_audit", {}).get("status")
        if roll_status != "verified":
            blockers.append("futures_roll_audit:" + str(roll_status or "missing"))
    return blockers


def run_confirmatory_manifest(payload, paths=1000, replicates=5000,
                              minimum_forecasts=250, block_length=5):
    freeze_date = date.fromisoformat(payload["freeze_date"])
    holdout_start = date.fromisoformat(payload["holdout_start"])
    holdout_end = date.fromisoformat(payload["holdout_end"])
    if holdout_start <= freeze_date:
        raise ValueError("holdout_start must be strictly later than the protocol freeze_date")
    if holdout_end < holdout_start:
        raise ValueError("holdout_end must not be earlier than holdout_start")
    candidates = [item for item in payload.get("datasets", [])
                  if item.get("confirmatory_candidate", True)]
    if not candidates:
        raise ValueError("confirmatory manifest contains no candidate datasets")
    acceptance = payload["acceptance_criteria"]
    frozen = payload["frozen_model_configuration"]
    if len(candidates) < int(acceptance["minimum_family_coverage"]):
        raise ValueError("candidate family is smaller than the pre-registered minimum coverage")
    if paths != int(frozen["paths_per_forecast"]):
        raise ValueError("paths differs from the frozen protocol configuration")
    if replicates != int(acceptance["bootstrap_replicates"]):
        raise ValueError("bootstrap replicates differ from the pre-registered protocol")
    if minimum_forecasts != int(acceptance["minimum_oos_forecasts_per_instrument"]):
        raise ValueError("minimum forecast count differs from the pre-registered protocol")
    if block_length != int(acceptance["block_length_observations"]):
        raise ValueError("block length differs from the pre-registered protocol")
    frozen_item_fields = {
        "horizon": "horizon_observations",
        "min_train": "min_train_observations",
        "estimation_window": "estimation_window",
        "calibration_window": "calibration_window",
        "min_calibration_observations": "min_calibration_observations",
    }
    for item in candidates:
        for item_field, frozen_field in frozen_item_fields.items():
            if int(item.get(item_field, frozen[frozen_field])) != int(frozen[frozen_field]):
                raise ValueError(
                    f"{item['instrument_id']} overrides frozen setting {item_field}"
                )

    precondition_failures = []
    awaiting = []
    prepared = []
    for item in candidates:
        evaluated = evaluate_dataset(item, paths=paths, data_only=True)
        blockers = _metadata_blockers(item, evaluated)
        if blockers:
            precondition_failures.append({
                "instrument_id": item["instrument_id"],
                "blockers": blockers,
                "provider_status": evaluated.get("status"),
            })
            continue
        timestamps = evaluated.get("observation_timestamps", [])
        prices = evaluated.pop("_prices", [])
        first_origin = max(
            int(item.get("min_train", 252)),
            int(item.get("estimation_window", 252)),
        )
        horizon = int(item.get("horizon", 5))
        potential_origins = [
            index for index in range(first_origin, max(first_origin, len(prices) - horizon))
            if index < len(timestamps)
            and holdout_start.isoformat() <= str(timestamps[index])[:10] <= holdout_end.isoformat()
        ]
        prepared.append({
            "item": item,
            "evaluated": evaluated,
            "prices": prices,
            "timestamps": timestamps,
            "potential_forecast_count": len(potential_origins),
        })
        if len(potential_origins) < minimum_forecasts:
            awaiting.append({
                "instrument_id": item["instrument_id"],
                "holdout_forecasts_available": len(potential_origins),
                "minimum_required": minimum_forecasts,
                "holdout_start": holdout_start.isoformat(),
                "latest_observation": (
                    str(timestamps[-1]) if timestamps else None
                ),
                "holdout_window_complete": bool(
                    timestamps and str(timestamps[-1])[:10] >= holdout_end.isoformat()
                ),
            })

    report = {
        "report_type": "pre_registered_confirmatory_oos",
        "protocol_id": payload.get("protocol_id"),
        "protocol_status": payload.get("status"),
        "freeze_date": freeze_date.isoformat(),
        "holdout_start": holdout_start.isoformat(),
        "holdout_end": holdout_end.isoformat(),
        "paths_per_forecast": paths,
        "bootstrap_replicates": replicates,
        "block_length": block_length,
        "minimum_forecasts_per_instrument": minimum_forecasts,
        "pre_registered_family": [x["instrument_id"] for x in candidates],
        "pre_registered_family_size": len(candidates),
        "excluded_candidates": payload.get("blocked_candidates", []),
        "precondition_failures": precondition_failures,
        "awaiting_future_holdout": awaiting,
        "results": [],
        "limitations": [
            "No historical data before holdout_start is scored; it is used only for estimation and matured calibration.",
            "The holdout is genuinely future-dated relative to the protocol freeze date.",
            "The Brier Skill test is a probability-score comparison, not a profitability or investment-performance test.",
            "All pre-registered candidates must be available; missing instruments are not silently dropped.",
            "Market calendars are declared in metadata but still require independent session/holiday verification.",
        ],
    }

    if precondition_failures:
        report["status"] = "blocked_preconditions"
        return report
    if len(prepared) != len(candidates):
        report["status"] = "blocked_incomplete_family"
        return report
    if awaiting:
        report["status"] = (
            "insufficient_confirmatory_sample"
            if all(x["holdout_window_complete"] for x in awaiting)
            else "awaiting_future_holdout"
        )
        return report

    results = []
    for entry in prepared:
        item = entry["item"]
        evaluated = entry["evaluated"]
        prices = entry["prices"]
        diagnostic = walk_forward_barrier_diagnostic(
            prices,
            entry_offset=float(frozen.get("entry_offset", 0.0)),
            target_pct=float(frozen["target_pct"]),
            stop_pct=float(frozen["stop_pct"]),
            horizon=int(frozen["horizon_observations"]),
            min_train=int(frozen["min_train_observations"]),
            paths=paths,
            seed=int(frozen["seed"]),
            drift_convention=frozen.get("drift_convention", "corrected"),
            estimation_window=int(frozen["estimation_window"]),
            calibration_window=int(frozen["calibration_window"]),
            min_calibration_observations=int(frozen["min_calibration_observations"]),
            min_calibration_improvement=float(frozen["min_calibration_improvement"]),
            periods_per_year=int(evaluated["manifest"]["effective_periods_per_year"]),
            step_year_fraction=float(item.get(
                "step_year_fraction",
                1.0 / int(evaluated["manifest"]["effective_periods_per_year"]),
            )),
        )
        rows = []
        for row in diagnostic["rows"]:
            origin_index = int(row["index"])
            origin_date = str(entry["timestamps"][origin_index])[:10]
            if holdout_start.isoformat() <= origin_date <= holdout_end.isoformat():
                scored = dict(row)
                scored["origin_date"] = origin_date
                rows.append(scored)
        if len(rows) < minimum_forecasts:
            raise RuntimeError(
                "confirmatory holdout became incomplete while scoring "
                + item["instrument_id"]
            )
        model_total = sum(float(x["brier_score"]) for x in rows)
        baseline_total = sum(float(x["baseline_brier_score"]) for x in rows)
        skill = 1.0 - model_total / baseline_total if baseline_total > 0 else None
        bootstrap = block_bootstrap_skill_interval(
            rows, block_length=block_length, replicates=replicates,
            seed=20261126 + sum(ord(ch) for ch in item["instrument_id"]),
        )
        results.append({
            "instrument_id": item["instrument_id"],
            "asset_class": item["asset_class"],
            "interval": item["interval"],
            "provider": evaluated.get("provider"),
            "source_sha256": evaluated.get("source_sha256"),
            "data_sha256": evaluated.get("data_sha256"),
            "holdout_start": rows[0]["origin_date"],
            "holdout_end": rows[-1]["origin_date"],
            "oos_forecasts": len(rows),
            "brier_skill_score": skill,
            "bootstrap": bootstrap,
        })
    _holm_adjust(results)
    for item in results:
        ci = item["bootstrap"].get("brier_skill_ci_95", [None, None])
        item["instrument_pass"] = bool(
            item["bootstrap"].get("status") == "estimated"
            and ci[0] is not None and ci[0] > 0
            and item.get("holm_adjusted_p_value", 1.0) < float(
                acceptance["alpha"]
            )
        )
    report["results"] = results
    report["status"] = (
        "confirmatory_family_pass" if all(x["instrument_pass"] for x in results)
        else "not_confirmed"
    )
    report["family_pass"] = all(x["instrument_pass"] for x in results)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", default="datasets/confirmatory_oos_manifest.json")
    parser.add_argument("--paths", type=int, default=1000)
    parser.add_argument("--replicates", type=int, default=5000)
    parser.add_argument("--minimum-forecasts", type=int, default=250)
    parser.add_argument("--block-length", type=int, default=5)
    parser.add_argument("--output", default="confirmatory_oos_report.json")
    args = parser.parse_args()
    if min(args.paths, args.replicates, args.minimum_forecasts, args.block_length) < 1:
        parser.error("paths, replicates, minimum forecasts, and block length must be positive")
    manifest_path = Path(args.manifest)
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    report = run_confirmatory_manifest(
        payload, paths=args.paths, replicates=args.replicates,
        minimum_forecasts=args.minimum_forecasts, block_length=args.block_length,
    )
    report["manifest_sha256"] = hashlib.sha256(
        manifest_path.read_bytes()
    ).hexdigest()
    output_path = Path(args.output)
    output_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    print(f"Saved report: {output_path}")


if __name__ == "__main__":
    main()
