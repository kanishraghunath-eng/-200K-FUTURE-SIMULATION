"""Dependence-aware uncertainty analysis for manifest-driven OOS reports.

The output is exploratory statistical evidence, not a profitability test.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np


def block_bootstrap_skill_interval(rows, block_length=5, replicates=2000, seed=20261126):
    """Circular moving-block bootstrap for paired Brier skill versus baseline."""
    n = len(rows)
    if block_length < 1 or replicates < 100:
        raise ValueError("block_length must be positive and replicates must be >= 100")
    if n < max(20, 4 * block_length):
        return {"status": "insufficient_sample", "forecast_count": n}

    differences = np.asarray(
        [float(row["baseline_brier_score"]) - float(row["brier_score"])
         for row in rows], dtype=float
    )
    baselines = np.asarray(
        [float(row["baseline_brier_score"]) for row in rows], dtype=float
    )
    if not np.isfinite(differences).all() or not np.isfinite(baselines).all():
        return {"status": "invalid_scores", "forecast_count": n}
    if float(baselines.mean()) <= 0:
        return {"status": "invalid_baseline", "forecast_count": n}

    observed_skill = float(differences.mean() / baselines.mean())
    rng = np.random.default_rng(seed)
    blocks_per_sample = math.ceil(n / block_length)
    offsets = np.arange(block_length)
    skill_samples = np.empty(replicates, dtype=float)
    null_tail_count = 0
    batch_size = 64

    for batch_start in range(0, replicates, batch_size):
        batch_count = min(batch_size, replicates - batch_start)
        starts = rng.integers(0, n, size=(batch_count, blocks_per_sample))
        indices = ((starts[:, :, None] + offsets[None, None, :]) % n)
        indices = indices.reshape(batch_count, -1)[:, :n]
        mean_difference = differences[indices].mean(axis=1)
        mean_baseline = baselines[indices].mean(axis=1)
        valid = mean_baseline > 0
        if not valid.all():
            return {"status": "invalid_bootstrap_baseline", "forecast_count": n}
        batch_skills = mean_difference / mean_baseline
        skill_samples[batch_start:batch_start + batch_count] = batch_skills
        null_tail_count += int(np.count_nonzero(mean_difference <= 0))

    low, high = np.quantile(skill_samples, [0.025, 0.975])
    return {
        "status": "estimated",
        "forecast_count": n,
        "block_length": block_length,
        "replicates": replicates,
        "brier_skill_score": observed_skill,
        "brier_skill_ci_95": [float(low), float(high)],
        "one_sided_bootstrap_p_value": float((null_tail_count + 1) / (replicates + 1)),
        "interpretation": "Exploratory circular moving-block bootstrap; not a profitability or trading-performance test.",
    }


def apply_holm_adjustment(results):
    """Attach Holm family-wise adjusted p-values to evaluated instruments."""
    valid = [(float(item["bootstrap"]["one_sided_bootstrap_p_value"]), i)
             for i, item in enumerate(results)
             if item.get("bootstrap", {}).get("one_sided_bootstrap_p_value") is not None]
    valid.sort(key=lambda pair: pair[0])
    family_size = len(valid)
    running_max = 0.0
    for rank, (p_value, index) in enumerate(valid):
        adjusted = min(1.0, (family_size - rank) * p_value)
        running_max = max(running_max, adjusted)
        results[index]["bootstrap"]["holm_adjusted_p_value"] = running_max
        results[index]["bootstrap"]["holm_family_size"] = family_size
        results[index]["bootstrap"]["holm_family"] = "all evaluated instruments in this manifest report"
    return results


def analyze_report(payload, replicates=2000, block_length=5, seed=20261126):
    results = []
    skipped = []
    for index, dataset in enumerate(payload.get("datasets", [])):
        if dataset.get("status") != "evaluated":
            skipped.append({
                "instrument_id": dataset.get("instrument_id"),
                "status": dataset.get("status"),
                "provider": dataset.get("provider"),
                "reason": dataset.get("error") or "dataset was not evaluated",
            })
            continue
        diagnostic = dataset.get("oos_diagnostic", {})
        rows = diagnostic.get("rows", [])
        bootstrap = block_bootstrap_skill_interval(
            rows, block_length=block_length, replicates=replicates,
            seed=seed + index,
        )
        results.append({
            "instrument_id": dataset.get("instrument_id"),
            "asset_class": dataset.get("asset_class"),
            "interval": dataset.get("manifest", {}).get("interval"),
            "provider": dataset.get("provider"),
            "source_sha256": dataset.get("source_sha256"),
            "data_sha256": dataset.get("data_sha256"),
            "oos_forecasts": len(rows),
            "multiclass_brier_score": diagnostic.get("multiclass_brier_score"),
            "baseline_multiclass_brier_score": diagnostic.get("baseline_multiclass_brier_score"),
            "brier_skill_score": diagnostic.get("brier_skill_score"),
            "bootstrap": bootstrap,
        })
    apply_holm_adjustment(results)
    return {
        "report_type": "manifest_oos_statistical_uncertainty",
        "method": "Circular moving-block bootstrap of paired per-forecast Brier differences",
        "block_length_observations": block_length,
        "bootstrap_replicates": replicates,
        "seed": seed,
        "evaluated_instrument_count": len(results),
        "skipped_dataset_count": len(skipped),
        "multiple_comparison_method": "Holm family-wise adjustment across evaluated instruments",
        "results": results,
        "skipped_datasets": skipped,
        "limitations": [
            "The block length is set to the forecast outcome horizon and may not capture longer-range dependence.",
            "Confidence intervals are exploratory and do not establish causal model superiority.",
            "Brier skill measures probability score versus a causal baseline, not price accuracy, directional hit rate, or profitability.",
            "A new untouched confirmatory holdout and pre-registered acceptance criteria are still required.",
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Manifest-driven OOS JSON report")
    parser.add_argument("--output", default="multi_asset_oos_uncertainty.json")
    parser.add_argument("--replicates", type=int, default=2000)
    parser.add_argument("--block-length", type=int, default=5)
    parser.add_argument("--seed", type=int, default=20261126)
    args = parser.parse_args()
    if args.replicates < 100 or args.block_length < 1:
        parser.error("--replicates must be >= 100 and --block-length must be positive")

    input_path = Path(args.input)
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    report = analyze_report(payload, args.replicates, args.block_length, args.seed)
    report["input_report_sha256"] = hashlib.sha256(input_path.read_bytes()).hexdigest()
    output_path = Path(args.output)
    output_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    print(f"Saved report: {output_path}")


if __name__ == "__main__":
    main()
