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
    if evaluated.get("status") != "evaluated":
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
    if holdout_start <= freeze_date:
        raise ValueError("holdout_start must be strictly later than the protocol freeze_date")
    candidates = [item for item in payload.get("datasets", [])
                  if item.get("confirmatory_candidate", True)]
    if not candidates:
        raise ValueError("confirmatory manifest contains no candidate datasets")

    precondition_failures = []
    awaiting = []
    prepared = []
    for item in candidates:
        evaluated = evaluate_dataset(item, paths=paths)
        blockers = _metadata_blockers(item, evaluated)
        if blockers:
            precondition_failures.append({
                "instrument_id": item["instrument_id"],
                "blockers": blockers,
                "provider_status": evaluated.get("status"),
            })
            continue
        timestamps = evaluated.get("observation_timestamps", [])
        diagnostic_rows = evaluated.get("oos_diagnostic", {}).get("rows", [])
        holdout_rows = []
        for row in diagnostic_rows:
            index = int(row["index"])
            if index < 0 or index >= len(timestamps):
                precondition_failures.append({
                    "instrument_id": item["instrument_id"],
                    "blockers": ["forecast_index_outside_observation_timestamps"],
                })
                holdout_rows = []
                break
            origin_date = str(timestamps[index])[:10]
            if origin_date >= holdout_start.isoformat():
                scored = dict(row)
                scored["origin_date"] = origin_date
                holdout_rows.append(scored)
        prepared.append({
            "item": item,
            "evaluated": evaluated,
            "holdout_rows": holdout_rows,
        })
        if len(holdout_rows) < minimum_forecasts:
            awaiting.append({
                "instrument_id": item["instrument_id"],
                "holdout_forecasts_available": len(holdout_rows),
                "minimum_required": minimum_forecasts,
                "holdout_start": holdout_start.isoformat(),
                "latest_observation": (
                    str(timestamps[-1]) if timestamps else None
                ),
            })

    report = {
        "report_type": "pre_registered_confirmatory_oos",
        "protocol_id": payload.get("protocol_id"),
        "protocol_status": payload.get("status"),
        "freeze_date": freeze_date.isoformat(),
        "holdout_start": holdout_start.isoformat(),
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
        report["status"] = "awaiting_future_holdout"
        return report

    results = []
    for entry in prepared:
        item = entry["item"]
        rows = entry["holdout_rows"]
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
            "provider": entry["evaluated"].get("provider"),
            "source_sha256": entry["evaluated"].get("source_sha256"),
            "data_sha256": entry["evaluated"].get("data_sha256"),
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
                payload["acceptance_criteria"]["alpha"]
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
