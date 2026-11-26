"""Multi-market, held-out walk-forward calibration and Monte Carlo stability study.

Yahoo Finance chart data are adjusted-close snapshots from a third-party service.
This is a reproducible research diagnostic, not investment advice or a profitability test.
"""
import argparse
import csv
import hashlib
import json
import math
import os
import random
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.backtest import walk_forward_barrier_diagnostic  # noqa: E402
from engine.monte_carlo import simulate_price_paths, barrier_probabilities  # noqa: E402

SYMBOLS = {
    "SPY": "US large-cap equities",
    "QQQ": "US Nasdaq-100 equities",
    "IWM": "US small-cap equities",
    "EFA": "Developed international equities",
    "EEM": "Emerging-market equities",
    "TLT": "US long-duration Treasury bonds",
}
FOLDS = [
    {"name": "Pre-GFC", "start": "2006-01-03", "end": "2006-06-30"},
    {"name": "Global financial crisis", "start": "2008-07-01", "end": "2008-12-31"},
    {"name": "2015 volatility", "start": "2015-07-01", "end": "2015-12-31"},
    {"name": "COVID shock and rebound", "start": "2020-01-02", "end": "2020-06-30"},
    {"name": "2022 tightening/bear", "start": "2022-01-03", "end": "2022-06-30"},
    {"name": "Recent holdout H1", "start": "2024-01-02", "end": "2024-06-28"},
    {"name": "Recent holdout H2", "start": "2024-07-01", "end": "2024-12-31"},
    {"name": "2025 holdout", "start": "2025-01-02", "end": "2025-12-31"},
    {"name": "2026 holdout YTD", "start": "2026-01-02", "end": "2026-11-25"},
]
GATES = (0.0, 0.005, 0.01, 0.02)
CONVERGENCE_SEEDS = (7, 101, 2026)
ESTIMATION = 252
CALIBRATION_WARMUP = 110
HORIZON = 5
TARGET = 0.02
STOP = 0.02
MIN_CALIBRATION = 100


def fetch_adjusted_close(symbol):
    period1 = int(datetime(2000, 1, 1, tzinfo=timezone.utc).timestamp())
    period2 = int(datetime.now(timezone.utc).timestamp())
    query = urllib.parse.urlencode({
        "period1": period1, "period2": period2, "interval": "1d",
        "events": "div,splits", "includeAdjustedClose": "true",
    })
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?{query}"
    request = urllib.request.Request(
        url, headers={"User-Agent": "200k-future-simulation-research/1.0",
                      "Accept": "application/json"}
    )
    last_error = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                raw = response.read()
            payload = json.loads(raw.decode("utf-8"))
            chart = payload.get("chart", {})
            if chart.get("error"):
                raise ValueError(f"{symbol}: Yahoo chart error: {chart['error']}")
            result = chart.get("result")
            if not result:
                raise ValueError(f"{symbol}: no chart result")
            item = result[0]
            timestamps = item.get("timestamp") or []
            adjusted = item.get("indicators", {}).get("adjclose", [{}])[0].get("adjclose")
            if not adjusted or len(timestamps) != len(adjusted):
                raise ValueError(f"{symbol}: adjusted-close series missing or misaligned")
            rows = []
            for stamp, value in zip(timestamps, adjusted):
                if value is None:
                    continue
                date = datetime.fromtimestamp(stamp, timezone.utc).date().isoformat()
                price = float(value)
                if price <= 0:
                    raise ValueError(f"{symbol}: non-positive adjusted close at {date}")
                rows.append((date, price))
            if len(rows) < 1000:
                raise ValueError(f"{symbol}: unexpectedly short history ({len(rows)} rows)")
            if any(rows[i][0] >= rows[i + 1][0] for i in range(len(rows) - 1)):
                raise ValueError(f"{symbol}: dates are duplicated or not increasing")
            return raw, rows, url
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt == 3:
                break
            time.sleep(2 ** attempt)
    raise RuntimeError(f"{symbol}: data download failed: {last_error}")


def block_bootstrap_skill_interval(rows, block_length=HORIZON, replicates=2000, seed=7):
    """Circular moving-block bootstrap for paired Brier skill differences.

    Blocks preserve short-range dependence from overlapping forecast horizons.
    This is exploratory uncertainty, not a confirmatory p-value.
    """
    n = len(rows)
    if n < max(20, 4 * block_length):
        return {"status": "insufficient_sample", "block_length": block_length}
    segments = {}
    for row in rows:
        segment = row.get("_bootstrap_segment", "all")
        segments.setdefault(segment, []).append(row)
    segment_values = []
    for segment_rows in segments.values():
        segment_values.append((
            [float(x["baseline_brier_score"]) - float(x["brier_score"])
             for x in segment_rows],
            [float(x["baseline_brier_score"]) for x in segment_rows],
        ))
    observed_difference = sum(sum(x[0]) for x in segment_values) / n
    observed_baseline = sum(sum(x[1]) for x in segment_values) / n
    if observed_baseline <= 0:
        return {"status": "invalid_baseline", "block_length": block_length}

    rng = random.Random(seed)
    skill_samples = []
    null_tail = 0
    for _ in range(replicates):
        sampled_differences = []
        sampled_baselines = []
        for differences, baselines in segment_values:
            segment_n = len(differences)
            blocks_per_sample = math.ceil(segment_n / block_length)
            indices = []
            for _ in range(blocks_per_sample):
                start = rng.randrange(segment_n)
                indices.extend((start + offset) % segment_n
                               for offset in range(block_length))
            indices = indices[:segment_n]
            sampled_differences.extend(differences[i] for i in indices)
            sampled_baselines.extend(baselines[i] for i in indices)
        mean_difference = sum(sampled_differences) / n
        mean_baseline = sum(sampled_baselines) / n
        if mean_baseline > 0:
            skill_samples.append(mean_difference / mean_baseline)
        if mean_difference <= 0:
            null_tail += 1

    skill_samples.sort()
    if not skill_samples:
        return {"status": "bootstrap_failed", "block_length": block_length}
    low = skill_samples[int(0.025 * (len(skill_samples) - 1))]
    high = skill_samples[int(0.975 * (len(skill_samples) - 1))]
    return {
        "status": "estimated",
        "block_length": block_length,
        "replicates": len(skill_samples),
        "brier_skill_ci_95": [low, high],
        "one_sided_bootstrap_p_value": (null_tail + 1) / (replicates + 1),
        "interpretation": "Circular moving-block bootstrap; exploratory and not adjusted for multiple comparisons.",
    }


def score_rows(rows, bootstrap=False, bootstrap_seed=7):
    if not rows:
        raise ValueError("cannot score an empty OOS sample")
    n = len(rows)
    result = {
        "oos_forecasts": n,
        "raw_brier": sum(x["raw_brier_score"] for x in rows) / n,
        "baseline_brier": sum(x["baseline_brier_score"] for x in rows) / n,
        "calibrated_brier": sum(x["brier_score"] for x in rows) / n,
        "brier_skill_vs_baseline": (
            1.0 - sum(x["brier_score"] for x in rows) /
            sum(x["baseline_brier_score"] for x in rows)
            if sum(x["baseline_brier_score"] for x in rows) > 0 else None
        ),
        "alpha_counts": {
            str(a): sum(1 for x in rows if abs(x["calibration_alpha"] - a) < 1e-12)
            for a in sorted({x["calibration_alpha"] for x in rows})
        },
    }
    if bootstrap:
        result["block_bootstrap"] = block_bootstrap_skill_interval(
            rows, block_length=HORIZON, replicates=2000, seed=bootstrap_seed
        )
    return result


def apply_holm_adjustment(datasets):
    """Apply Holm family-wise adjustment to per-instrument/per-gate bootstrap p-values."""
    tests = []
    for symbol, item in datasets.items():
        for gate, score in item["oos_validation"]["aggregate_oos_by_gate"].items():
            boot = score.get("block_bootstrap", {})
            p_value = boot.get("one_sided_bootstrap_p_value")
            if p_value is not None:
                tests.append((float(p_value), symbol, gate))
    tests.sort(key=lambda item: item[0])
    family_size = len(tests)
    running_max = 0.0
    for rank, (p_value, symbol, gate) in enumerate(tests):
        adjusted = min(1.0, (family_size - rank) * p_value)
        running_max = max(running_max, adjusted)
        score = datasets[symbol]["oos_validation"]["aggregate_oos_by_gate"][gate]
        score["block_bootstrap"]["holm_adjusted_p_value"] = running_max
        score["block_bootstrap"]["holm_family_size"] = family_size
        score["block_bootstrap"]["holm_family"] = "all instrument x calibration-gate comparisons in this study"


def evaluate_oos(dataset_rows, paths):
    dates = [x[0] for x in dataset_rows]
    closes = [x[1] for x in dataset_rows]
    by_gate = {str(g): [] for g in GATES}
    skipped = []
    fold_results = []
    minimum_prefix = ESTIMATION + CALIBRATION_WARMUP

    for fold in FOLDS:
        start = next((i for i, d in enumerate(dates) if d >= fold["start"]), None)
        end = next((i for i, d in enumerate(dates) if d > fold["end"]), len(dates))
        if start is None or start < minimum_prefix or end <= start:
            skipped.append({"fold": fold["name"], "reason": "insufficient pre-fold history or no observations"})
            continue

        segment_start = start - minimum_prefix
        segment = closes[segment_start:end]
        # The first 252 observations estimate the model; the next 110 produce
        # matured calibration forecasts. Only subsequent rows count as OOS.
        first_oos_index = minimum_prefix
        fold_gate_scores = {}
        for gate in GATES:
            result = walk_forward_barrier_diagnostic(
                segment, target_pct=TARGET, stop_pct=STOP, horizon=HORIZON,
                paths=paths, seed=7, periods_per_year=252,
                estimation_window=ESTIMATION, calibration_window=252,
                min_calibration_observations=MIN_CALIBRATION,
                min_calibration_improvement=gate,
            )
            oos_rows = [r for r in result["rows"] if r["index"] >= first_oos_index]
            for row in oos_rows:
                row["_bootstrap_segment"] = fold["name"]
            if not oos_rows:
                skipped.append({"fold": fold["name"], "reason": "no scored OOS forecasts"})
                continue
            score = score_rows(oos_rows)
            fold_gate_scores[str(gate)] = score
            by_gate[str(gate)].extend(oos_rows)
        fold_results.append({
            "fold": fold["name"],
            "requested_start": fold["start"],
            "requested_end": fold["end"],
            "actual_oos_start": dates[start],
            "actual_oos_end": dates[end - 1],
            "warmup_observations": minimum_prefix,
            "scores_by_gate": fold_gate_scores,
        })

    aggregate = {
        gate: score_rows(
            rows, bootstrap=True,
            bootstrap_seed=7 + sum((i + 1) * ord(ch) for i, ch in enumerate(str(gate)))
        ) if rows else {"status": "no OOS forecasts"}
        for gate, rows in by_gate.items()
    }
    return {"folds": fold_results, "aggregate_oos_by_gate": aggregate, "skipped": skipped}


def convergence_check(dataset_rows, samples_per_fold):
    dates = [x[0] for x in dataset_rows]
    closes = [x[1] for x in dataset_rows]
    comparisons = []
    for fold in FOLDS:
        start = next((i for i, d in enumerate(dates) if d >= fold["start"]), None)
        end = next((i for i, d in enumerate(dates) if d > fold["end"]), len(dates))
        if start is None or start < ESTIMATION + CALIBRATION_WARMUP or end <= start:
            continue
        available = list(range(start, max(start, end - HORIZON)))
        if not available:
            continue
        count = min(samples_per_fold, len(available))
        selected = [available[round(k * (len(available) - 1) / max(1, count - 1))]
                    for k in range(count)]
        for origin in selected:
            train = closes[max(0, origin - ESTIMATION + 1):origin + 1]
            entry = train[-1]
            target = entry * (1.0 + TARGET)
            stop = entry * (1.0 - STOP)
            for seed_base in CONVERGENCE_SEEDS:
                seed = seed_base + origin
                outputs = {}
                for n_paths in (5000, 10000):
                    sim = simulate_price_paths(
                        train, HORIZON, paths=n_paths, seed=seed,
                        drift_mode="historical", periods_per_year=252,
                        chunk_size=10000, return_paths=True,
                    )
                    outputs[str(n_paths)] = barrier_probabilities(
                        sim["paths"], entry, target, stop
                    )
                small, large = outputs["5000"], outputs["10000"]
                keys = ("target_first_probability", "stop_first_probability",
                        "neither_probability", "same_step_ambiguous_probability")
                comparisons.append({
                    "fold": fold["name"],
                    "origin_date": dates[origin],
                    "seed_base": seed_base,
                    "seed": seed,
                    "probability_abs_differences": {
                        key: abs(small[key] - large[key]) for key in keys
                    },
                    "mean_probability_abs_difference": sum(
                        abs(small[key] - large[key]) for key in keys[:3]
                    ) / 3.0,
                    "paths_5000": {key: small[key] for key in keys},
                    "paths_10000": {key: large[key] for key in keys},
                })
    diffs = sorted(x["mean_probability_abs_difference"] for x in comparisons)
    p95_index = min(len(diffs) - 1, math.ceil(0.95 * len(diffs)) - 1) if diffs else None
    return {
        "comparisons": comparisons,
        "sample_count": len(comparisons),
        "seed_bases": list(CONVERGENCE_SEEDS),
        "mean_abs_probability_difference": sum(diffs) / len(diffs) if diffs else None,
        "p95_abs_probability_difference": diffs[p95_index] if p95_index is not None else None,
        "max_abs_probability_difference": max(diffs) if diffs else None,
        "interpretation": "Monte Carlo sampling sensitivity across repeated seeds; not forecast accuracy.",
    }


def cross_provider_check(yahoo_rows, symbol="VTI"):
    """Compare Yahoo adjusted returns with EODHD adjusted returns for VTI."""
    public_url = f"https://eodhd.com/api/eod/{symbol}.US"
    query = urllib.parse.urlencode({
        "api_token": "demo", "from": min(x[0] for x in yahoo_rows),
        "to": max(x[0] for x in yahoo_rows), "period": "d", "fmt": "json",
    })
    request = urllib.request.Request(
        f"{public_url}?{query}",
        headers={"User-Agent": "200k-future-simulation-provider-check/1.0", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            status_code = getattr(response, "status", 200)
            raw = response.read().decode("utf-8", errors="replace")
        if status_code != 200:
            return {"status": "http_error", "http_status": status_code, "source_url": public_url}
        payload = json.loads(raw)
        if not isinstance(payload, list):
            return {"status": "invalid_response", "source_url": public_url}
        vendor = {}
        for row in payload:
            try:
                close = float(row.get("adjusted_close"))
            except (TypeError, ValueError):
                continue
            if row.get("date") and close > 0:
                vendor[str(row["date"])] = close
        yahoo = {d: float(v) for d, v in yahoo_rows}
        overlap = sorted(set(yahoo) & set(vendor))
        a, b = [], []
        for previous, current in zip(overlap, overlap[1:]):
            a.append(math.log(yahoo[current] / yahoo[previous]))
            b.append(math.log(vendor[current] / vendor[previous]))
        if len(a) < 100:
            return {"status": "insufficient_overlap", "overlapping_return_observations": len(a),
                    "yahoo_common_dates": len(overlap), "eodhd_observations": len(vendor),
                    "source_url": public_url, "price_basis": "split-and-dividend-adjusted close"}
        return {"status": "completed", "provider": "EODHD", "instrument": symbol + ".US",
                "overlapping_return_observations": len(a), "yahoo_common_dates": len(overlap),
                "eodhd_observations": len(vendor),
                "pearson_daily_return_correlation": statistics.correlation(a, b),
                "daily_return_sign_agreement": sum((x >= 0) == (y >= 0) for x, y in zip(a, b)) / len(a),
                "median_absolute_daily_log_return_difference": statistics.median(abs(x-y) for x, y in zip(a, b)),
                "source_url": public_url, "price_basis": "split-and-dividend-adjusted close on both sources"}
    except urllib.error.HTTPError as exc:
        status = "access_denied" if exc.code in (401, 403) else "rate_limited" if exc.code == 429 else "http_error"
        return {"status": status, "http_status": exc.code, "source_url": public_url}
    except (urllib.error.URLError, TimeoutError):
        return {"status": "unavailable", "source_url": public_url}
    except Exception as exc:
        return {"status": "invalid_response", "error_type": type(exc).__name__, "source_url": public_url}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paths", type=int, default=1000,
                        help="paths per origin for OOS calibration scoring")
    parser.add_argument("--convergence-samples-per-fold", type=int, default=4)
    parser.add_argument("--output", default="multi_market_oos_report.json")
    args = parser.parse_args()
    if args.paths < 1 or args.convergence_samples_per_fold < 1:
        parser.error("paths and convergence sample count must be positive")

    datasets = {}
    raw_rows_by_symbol = {}
    for symbol, market in SYMBOLS.items():
        raw, rows, source_url = fetch_adjusted_close(symbol)
        raw_rows_by_symbol[symbol] = rows
        datasets[symbol] = {
            "market": market,
            "source_url": source_url,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "observations": len(rows),
            "first_date": rows[0][0],
            "last_date": rows[-1][0],
            "corporate_action_basis": "Yahoo adjusted-close field; not independently audited",
            "oos_validation": evaluate_oos(rows, args.paths),
            "monte_carlo_convergence": convergence_check(
                rows, args.convergence_samples_per_fold
            ),
        }

    aggregate_by_gate = defaultdict(list)
    for item in datasets.values():
        for gate, score in item["oos_validation"]["aggregate_oos_by_gate"].items():
            if "calibrated_brier" in score:
                aggregate_by_gate[gate].append(score)

    combined = {}
    for gate, scores in aggregate_by_gate.items():
        total_n = sum(x["oos_forecasts"] for x in scores)
        raw = sum(x["raw_brier"] * x["oos_forecasts"] for x in scores) / total_n
        baseline = sum(x["baseline_brier"] * x["oos_forecasts"] for x in scores) / total_n
        calibrated = sum(x["calibrated_brier"] * x["oos_forecasts"] for x in scores) / total_n
        combined[gate] = {
            "oos_forecasts": total_n,
            "raw_brier": raw,
            "baseline_brier": baseline,
            "calibrated_brier": calibrated,
            "brier_skill_vs_baseline": 1.0 - calibrated / baseline if baseline > 0 else None,
        }

    # Correct for the family of instrument x calibration-gate comparisons.
    apply_holm_adjustment(datasets)

    # VTI is in EODHD documented demo coverage; compare independent adjusted-return series.
    try:
        _, yahoo_vti_rows, yahoo_vti_url = fetch_adjusted_close("VTI")
        provider_result = cross_provider_check(yahoo_vti_rows, symbol="VTI")
        provider_result["yahoo_source_url"] = yahoo_vti_url
    except Exception as exc:
        provider_result = {"status": "yahoo_reference_unavailable", "error_type": type(exc).__name__}

    report = {
        "study": "multi-market held-out walk-forward calibration and Monte Carlo path-count stability",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "data_provider": "Yahoo Finance chart endpoint",
        "data_provider_note": "One third-party provider across multiple instruments; not independent vendor replication.",
        "settings": {
            "oos_paths_per_origin": args.paths,
            "convergence_path_counts": [5000, 10000],
            "convergence_samples_per_fold_per_instrument": args.convergence_samples_per_fold,
            "convergence_random_seeds": list(CONVERGENCE_SEEDS),
            "symbols": SYMBOLS,
            "folds": FOLDS,
            "estimation_window_observations": ESTIMATION,
            "calibration_warmup_forecasts": CALIBRATION_WARMUP,
            "calibration_window_forecasts": 252,
            "minimum_matured_calibration_forecasts": MIN_CALIBRATION,
            "horizon_observations": HORIZON,
            "target_barrier": TARGET,
            "stop_barrier": STOP,
            "calibration_gates": list(GATES),
            "uncertainty_method": "2,000-replicate circular moving-block bootstrap; block length equals the 5-observation label horizon",
            "multiple_comparison_method": "Holm adjustment across all instrument x calibration-gate comparisons",
            "oos_scoring_rule": "Only forecasts after the 252-observation estimation and 110-observation calibration warm-up are scored; each forecast uses only prior matured outcomes.",
            "default_changed": False,
        },
        "datasets": datasets,
        "independent_provider_crosscheck": {
            "instrument": "VTI",
            "reference_provider": "Yahoo Finance adjusted close",
            "comparison_provider": "EODHD adjusted close",
            "result": provider_result,
        },
        "combined_oos_by_gate": combined,
        "decision": "No default recommendation is made automatically; review cross-market and cross-period consistency, sample sizes, source caveats, and path-count sensitivity.",
        "limitations": [
            "Close-only barrier labels; same-bar OHLC ordering is not modeled.",
            "Transaction costs, spreads, slippage, taxes, and execution constraints are not modeled.",
            "Adjusted-close history is supplied by one third-party data provider and is not independently audited.",
            "This is a statistical research diagnostic, not a profitability test or investment recommendation.",
        ],
    }
    output = Path(args.output)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    print(f"Saved report: {output}")


if __name__ == "__main__":
    main()
