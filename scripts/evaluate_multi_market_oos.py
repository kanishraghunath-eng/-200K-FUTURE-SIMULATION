"""Multi-market, held-out walk-forward calibration and Monte Carlo stability study.

Yahoo Finance chart data are adjusted-close snapshots from a third-party service.
This is a reproducible research diagnostic, not investment advice or a profitability test.
"""
import argparse
import hashlib
import json
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
    {"name": "Recent holdout", "start": "2024-01-02", "end": "2024-06-28"},
]
GATES = (0.0, 0.005, 0.01, 0.02)
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


def score_rows(rows):
    if not rows:
        raise ValueError("cannot score an empty OOS sample")
    n = len(rows)
    return {
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
        gate: score_rows(rows) if rows else {"status": "no OOS forecasts"}
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
            seed = 7000 + origin
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
    diffs = [x["mean_probability_abs_difference"] for x in comparisons]
    return {
        "comparisons": comparisons,
        "sample_count": len(comparisons),
        "mean_abs_probability_difference": sum(diffs) / len(diffs) if diffs else None,
        "max_abs_probability_difference": max(diffs) if diffs else None,
        "interpretation": "Monte Carlo sampling sensitivity only; not forecast accuracy.",
    }


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
    for symbol, market in SYMBOLS.items():
        raw, rows, source_url = fetch_adjusted_close(symbol)
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

    report = {
        "study": "multi-market held-out walk-forward calibration and Monte Carlo path-count stability",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "data_provider": "Yahoo Finance chart endpoint",
        "data_provider_note": "One third-party provider across multiple instruments; not independent vendor replication.",
        "settings": {
            "oos_paths_per_origin": args.paths,
            "convergence_path_counts": [5000, 10000],
            "convergence_samples_per_fold_per_instrument": args.convergence_samples_per_fold,
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
            "oos_scoring_rule": "Only forecasts after the 252-observation estimation and 110-observation calibration warm-up are scored; each forecast uses only prior matured outcomes.",
            "default_changed": False,
        },
        "datasets": datasets,
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
