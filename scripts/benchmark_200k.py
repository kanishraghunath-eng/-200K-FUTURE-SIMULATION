"""Dedicated 200K-path runtime, memory and Monte Carlo convergence study.

Uses deterministic synthetic input to isolate engine performance from vendor
data availability. Results measure computation and sampling stability, not
forecast accuracy or trading performance.
"""
import argparse
import json
import math
import resource
import statistics
import time
from pathlib import Path

import numpy as np

import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine.monte_carlo import simulate_price_paths  # noqa: E402

PATH_COUNTS = (5_000, 10_000, 50_000, 200_000)
SEEDS = (7, 101, 2026)
HORIZONS = (5, 21, 252)
CHUNK_SIZE = 10_000
PROBABILITY_KEYS = ("target_first_probability", "stop_first_probability", "neither_probability")


def synthetic_history(seed=20261126, observations=1000):
    rng = np.random.default_rng(seed)
    log_returns = rng.normal(0.0002, 0.012, observations - 1)
    closes = 100.0 * np.exp(np.concatenate(([0.0], np.cumsum(log_returns))))
    return closes.tolist()


def run_case(prices, steps, paths, seed, chunk_size=CHUNK_SIZE):
    entry = float(prices[-1])
    started = time.perf_counter()
    result = simulate_price_paths(
        prices, steps=steps, paths=paths, seed=seed, chunk_size=chunk_size,
        periods_per_year=252, return_paths=False, entry=entry,
        target=entry * 1.02, stop=entry * 0.98,
    )
    elapsed = time.perf_counter() - started
    peak_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    peak_rss_bytes = int(peak_rss * (1024 if sys.platform != "darwin" else 1))
    return {
        "steps": steps, "paths": paths, "seed": seed,
        "elapsed_seconds": elapsed,
        "paths_per_second": paths / elapsed if elapsed > 0 else None,
        "process_peak_rss_bytes": peak_rss_bytes,
        "estimated_stream_chunk_bytes": int(chunk_size * (steps * 3 + steps + 1) * 8),
        "summary": result["summary"],
        "numerically_saturated": result["metadata"]["numerically_saturated"],
    }


def percentile(values, q):
    return float(np.quantile(np.asarray(values, dtype=float), q)) if values else None


def run_study():
    prices = synthetic_history()
    cache = {}
    performance = []
    for steps in HORIZONS:
        key = (steps, 200_000, SEEDS[0])
        case = run_case(prices, *key)
        cache[key] = case
        performance.append(case)

    convergence_rows = []
    for seed in SEEDS:
        for paths in PATH_COUNTS:
            key = (21, paths, seed)
            if key not in cache:
                cache[key] = run_case(prices, *key)
            convergence_rows.append(cache[key])

    errors = {str(paths): [] for paths in PATH_COUNTS[:-1]}
    for seed in SEEDS:
        reference = cache[(21, 200_000, seed)]["summary"]
        for paths in PATH_COUNTS[:-1]:
            sample = cache[(21, paths, seed)]["summary"]
            diffs = [abs(sample[k] - reference[k]) for k in PROBABILITY_KEYS]
            errors[str(paths)].append({
                "seed": seed,
                "mean_abs_probability_difference_vs_200k": sum(diffs) / len(diffs),
                "max_abs_probability_difference_vs_200k": max(diffs),
            })

    aggregate_errors = {}
    for paths, rows in errors.items():
        values = [x["mean_abs_probability_difference_vs_200k"] for x in rows]
        aggregate_errors[paths] = {
            "seed_results": rows,
            "mean_abs_probability_difference": statistics.mean(values),
            "p95_abs_probability_difference": percentile(values, 0.95),
            "max_abs_probability_difference": max(values),
        }

    seed_probabilities = {str(seed): cache[(21, 200_000, seed)]["summary"] for seed in SEEDS}
    seed_spread = {}
    for key in PROBABILITY_KEYS:
        values = [seed_probabilities[str(seed)][key] for seed in SEEDS]
        seed_spread[key] = {"min": min(values), "max": max(values), "range": max(values)-min(values)}

    return {
        "study": "200K paths performance and Monte Carlo convergence",
        "input": {"type": "deterministic synthetic price history", "observations": len(prices),
                  "seed": 20261126, "not_market_data": True},
        "settings": {"path_counts": list(PATH_COUNTS), "seeds": list(SEEDS),
                     "performance_horizons": list(HORIZONS), "convergence_horizon_steps": 21,
                     "chunk_size": CHUNK_SIZE, "storage_mode": "streamed_summary"},
        "performance_200k": performance,
        "convergence": {"reference_paths": 200000, "probability_metrics": list(PROBABILITY_KEYS),
                        "errors_vs_200k_by_path_count": aggregate_errors,
                        "200k_cross_seed_probability_spread": seed_spread,
                        "same_seed_prefix_comparison": True},
        "limitations": ["Synthetic input isolates compute performance; it does not validate market forecasts.",
                        "Monte Carlo convergence measures sampling stability, not real-world predictive accuracy.",
                        "Peak RSS is process high-water memory and includes Python/runtime overhead.",
                        "No trading profitability or investment conclusion is evaluated."],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="200k_benchmark_report.json")
    args = parser.parse_args()
    report = run_study()
    output = Path(args.output)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    print(f"Saved report: {output}")


if __name__ == "__main__":
    main()