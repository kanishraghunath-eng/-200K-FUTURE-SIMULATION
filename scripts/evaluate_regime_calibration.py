"""Run the repository's actual walk-forward calibration diagnostic across market regimes.

This is a reproducible research diagnostic, not a trading strategy or profitability test.
The external SPY CSV is a third-party snapshot; corporate-action adjustment status is
not independently verified. The default 1,000 paths keeps the CI run bounded.
"""
import argparse
import csv
import hashlib
import io
import json
import urllib.request
from collections import Counter
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from engine.backtest import walk_forward_barrier_diagnostic  # noqa: E402

DEFAULT_URL = (
    "https://raw.githubusercontent.com/gsl0001/"
    "daily-spy-data-from-2000-2025/main/spy_data.csv"
)
REGIMES = [
    {"name": "Dot-com bear (later phase)", "start": "2001-01-02", "end": "2002-10-09"},
    {"name": "Pre-GFC bull", "start": "2003-03-12", "end": "2007-10-09"},
    {"name": "Global financial crisis bear", "start": "2007-10-09", "end": "2009-03-09"},
    {"name": "Long bull", "start": "2010-01-04", "end": "2020-02-18"},
    {"name": "COVID high-volatility", "start": "2020-02-19", "end": "2020-04-30"},
    {"name": "2022 bear", "start": "2022-01-03", "end": "2022-10-12"},
    {"name": "2023-2025 recovery/bull", "start": "2023-01-03", "end": "2025-08-29"},
]


def load_prices(url):
    request = urllib.request.Request(url, headers={"User-Agent": "200k-future-simulation-regime-check/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        raw = response.read()
    text = raw.decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(text)))
    if len(rows) < 4:
        raise ValueError("CSV is shorter than the expected three metadata rows plus data")
    data = []
    for row in rows[3:]:
        if len(row) < 2:
            continue
        date, close_text = row[0].strip(), row[1].strip()
        if not date or not close_text:
            continue
        try:
            close = float(close_text)
        except ValueError:
            continue
        if close <= 0:
            raise ValueError(f"Non-positive close in source data at {date}")
        data.append((date, close))
    if not data or any(data[i][0] >= data[i + 1][0] for i in range(len(data) - 1)):
        raise ValueError("CSV dates are empty, duplicated, or not strictly increasing")
    return raw, data


def evaluate(data, paths, min_calibration_improvement=0.0):
    dates = [row[0] for row in data]
    closes = [row[1] for row in data]
    report = []
    estimation_window = 252
    horizon = 5
    for regime in REGIMES:
        start = next((i for i, d in enumerate(dates) if d >= regime["start"]), None)
        end = next((i for i, d in enumerate(dates) if d > regime["end"]), len(dates))
        if start is None or start < estimation_window or end <= start:
            report.append({"name": regime["name"], "status": "skipped", "reason": "insufficient source history"})
            continue
        # Include 252 pre-regime observations for model estimation; the first
        # scored forecast is exactly the first available observation in regime.
        segment = closes[start - estimation_window:end]
        result = walk_forward_barrier_diagnostic(
            segment,
            target_pct=0.02,
            stop_pct=0.02,
            horizon=horizon,
            paths=paths,
            seed=7,
            periods_per_year=252,
            estimation_window=estimation_window,
            calibration_window=252,
            min_calibration_observations=100,
            min_calibration_improvement=min_calibration_improvement,
        )
        alpha_counts = Counter(str(row["calibration_alpha"]) for row in result["rows"])
        report.append({
            "name": regime["name"],
            "status": "completed",
            "actual_start": dates[start],
            "actual_end": dates[end - 1],
            "observations": result["observations"],
            "raw_brier": result["raw_multiclass_brier_score"],
            "baseline_brier": result["baseline_multiclass_brier_score"],
            "calibrated_brier": result["multiclass_brier_score"],
            "brier_skill_vs_baseline": result["brier_skill_score"],
            "calibration_alpha_counts": dict(sorted(alpha_counts.items(), key=lambda x: float(x[0]))),
            "class_summary": result["class_summary"],
            "first_forecast_index": result["first_forecast_index"],
        })
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paths", type=int, default=1000)
    parser.add_argument("--dataset-url", default=DEFAULT_URL)
    parser.add_argument("--output", default="regime_calibration_report.json")
    args = parser.parse_args()
    if args.paths < 1:
        parser.error("--paths must be >= 1")
    raw, data = load_prices(args.dataset_url)
    result = {
        "dataset": {
            "source_url": args.dataset_url,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "observations": len(data),
            "first_date": data[0][0],
            "last_date": data[-1][0],
            "corporate_action_adjustment_status": "not independently verified",
        },
        "settings": {
            "paths_per_origin": args.paths,
            "horizon_observations": 5,
            "target_barrier": 0.02,
            "stop_barrier": 0.02,
            "estimation_window_observations": 252,
            "calibration_window_forecasts": 252,
            "minimum_matured_calibration_forecasts": 100,
            "minimum_calibration_improvement_grid": [0.0, 0.005, 0.01, 0.02],
            "random_seed": 7,
            "evaluation": "close-only walk-forward; not a profitability test",
        },
        "regime_comparison": {
            str(gate): evaluate(data, args.paths, min_calibration_improvement=gate)
            for gate in (0.0, 0.005, 0.01, 0.02)
        },
    }
    output = Path(args.output)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    print(f"Saved report: {output}")


if __name__ == "__main__":
    main()
