"""Close-only rolling walk-forward calibration diagnostics; not a trading strategy."""
import numpy as np
from .monte_carlo import simulate_price_paths, barrier_probabilities


def _barrier_class(prices, origin, horizon, entry_offset, target_pct, stop_pct):
    """Classify a fully observed historical window using close-only first touch."""
    entry = float(prices[origin] * (1.0 + entry_offset))
    target = entry * (1.0 + target_pct)
    stop = entry * (1.0 - stop_pct)
    future = prices[origin + 1:origin + 1 + horizon]
    target_hits = np.flatnonzero(future >= target)
    stop_hits = np.flatnonzero(future <= stop)
    if len(target_hits) and (not len(stop_hits) or target_hits[0] < stop_hits[0]):
        return 0
    if len(stop_hits):
        return 1
    return 2


def walk_forward_barrier_diagnostic(prices, entry_offset=0.0, target_pct=0.03, stop_pct=0.02,
                                    horizon=10, min_train=60, paths=5000, seed=7,
                                    drift_convention="corrected", periods_per_year=252,
                                    step_year_fraction=None, estimation_window=252,
                                    calibration_window=252, min_calibration_observations=100,
                                    min_calibration_improvement=0.0):
    """Evaluate rolling GBM forecasts with causal baseline and probability blending.

    The default estimation window is 252 observations. A convex blend between
    raw GBM probabilities and a rolling empirical baseline is fitted only on
    prior forecasts whose complete outcome horizons were observed before the
    current forecast origin. If calibration history is insufficient, the
    empirical baseline is used (blend weight zero).
    """
    p = np.asarray(prices, dtype=float)
    if p.ndim != 1 or len(p) < min_train + horizon + 3 or not np.isfinite(p).all() or (p <= 0).any():
        raise ValueError("insufficient or invalid prices for walk-forward diagnostic")
    if target_pct <= 0 or not 0 < stop_pct < 1 or horizon < 1:
        raise ValueError("invalid barrier or horizon settings")
    if not isinstance(periods_per_year, int) or periods_per_year <= 0:
        raise ValueError("periods_per_year must be a positive integer")
    if not isinstance(min_train, int) or min_train < 3:
        raise ValueError("min_train must be an integer >= 3")
    if not isinstance(estimation_window, int) or estimation_window < 3:
        raise ValueError("estimation_window must be an integer >= 3")
    if not isinstance(calibration_window, int) or calibration_window < 1:
        raise ValueError("calibration_window must be an integer >= 1")
    if not isinstance(min_calibration_observations, int) or min_calibration_observations < 1:
        raise ValueError("min_calibration_observations must be an integer >= 1")
    if (not np.isfinite(min_calibration_improvement)
            or not 0.0 <= min_calibration_improvement < 1.0):
        raise ValueError("min_calibration_improvement must be in [0, 1)")
    dt = (1.0 / periods_per_year) if step_year_fraction is None else float(step_year_fraction)
    if not np.isfinite(dt) or dt <= 0:
        raise ValueError("step_year_fraction must be a finite positive number")

    rows = []
    model_brier = []
    raw_brier = []
    baseline_brier = []
    class_actual = np.zeros(3, dtype=np.int64)
    class_predicted = np.zeros(3, dtype=float)
    class_raw_predicted = np.zeros(3, dtype=float)
    class_baseline = np.zeros(3, dtype=float)
    forecast_history = []
    first_origin = max(min_train, estimation_window)
    if len(p) <= first_origin + horizon:
        raise ValueError("insufficient prices for the requested estimation_window and horizon")

    alpha_grid = np.linspace(0.0, 1.0, 21)
    for i in range(first_origin, len(p) - horizon):
        train_start = max(0, i + 1 - estimation_window)
        train = p[train_start:i + 1]
        entry = float(train[-1] * (1 + entry_offset))
        target = entry * (1 + target_pct)
        stop = entry * (1 - stop_pct)

        sim = simulate_price_paths(
            train, horizon, paths=paths, seed=seed + i, drift_mode="historical",
            drift_convention=drift_convention, periods_per_year=periods_per_year,
            step_year_fraction=dt
        )
        pred = barrier_probabilities(sim["paths"], entry, target, stop)
        raw_probs = np.asarray([
            pred["target_first_probability"],
            pred["stop_first_probability"],
            pred["neither_probability"]
        ], dtype=float)

        actual = _barrier_class(p, i, horizon, entry_offset, target_pct, stop_pct)
        onehot = np.eye(3, dtype=float)[actual]

        # Historical outcomes are included only after their complete horizons end.
        history_start = max(0, i - estimation_window)
        historical_classes = [
            _barrier_class(p, j, horizon, entry_offset, target_pct, stop_pct)
            for j in range(history_start, i - horizon + 1)
        ]
        if historical_classes:
            counts = np.bincount(historical_classes, minlength=3).astype(float)
            baseline = counts / counts.sum()
        else:
            baseline = np.full(3, 1.0 / 3.0)

        # Fit a single convex blend weight on matured prior forecasts only.
        # forecast_history is chronological; exclude the latest horizon-1 forecasts.
        history_end = max(0, len(forecast_history) - horizon + 1)
        history_start_idx = max(0, history_end - calibration_window)
        calibration_rows = forecast_history[history_start_idx:history_end]
        alpha = 0.0
        if len(calibration_rows) >= min_calibration_observations:
            hist_raw = np.asarray([x["raw"] for x in calibration_rows], dtype=float)
            hist_base = np.asarray([x["baseline"] for x in calibration_rows], dtype=float)
            hist_onehot = np.eye(3, dtype=float)[
                np.asarray([x["actual"] for x in calibration_rows], dtype=int)
            ]
            best_score = float("inf")
            baseline_score = float(np.mean(np.sum((hist_base - hist_onehot) ** 2, axis=1)))
            for candidate in alpha_grid:
                mixed = candidate * hist_raw + (1.0 - candidate) * hist_base
                score = float(np.mean(np.sum((mixed - hist_onehot) ** 2, axis=1)))
                # Ascending grid and strict comparison favour the conservative blend on ties.
                if score < best_score - 1e-12:
                    best_score = score
                    alpha = float(candidate)
            # Require a minimum historical improvement before trusting a fitted blend.
            if best_score > baseline_score * (1.0 - min_calibration_improvement):
                alpha = 0.0

        calibrated = alpha * raw_probs + (1.0 - alpha) * baseline
        raw_score = float(np.sum((raw_probs - onehot) ** 2))
        calibrated_score = float(np.sum((calibrated - onehot) ** 2))
        baseline_score = float(np.sum((baseline - onehot) ** 2))
        raw_brier.append(raw_score)
        model_brier.append(calibrated_score)
        baseline_brier.append(baseline_score)
        class_actual[actual] += 1
        class_predicted += calibrated
        class_raw_predicted += raw_probs
        class_baseline += baseline

        rows.append({
            "index": i,
            "actual_class": ("target_first" if actual == 0 else
                             "stop_first" if actual == 1 else "neither"),
            "predicted": calibrated.tolist(),
            "raw_predicted": raw_probs.tolist(),
            "baseline_predicted": baseline.tolist(),
            "calibration_alpha": alpha,
            "calibration_observations": len(calibration_rows),
            "baseline_observations": len(historical_classes),
            "brier_score": calibrated_score,
            "raw_brier_score": raw_score,
            "baseline_brier_score": baseline_score
        })
        forecast_history.append({
            "index": i, "raw": raw_probs, "baseline": baseline, "actual": actual
        })

    count = len(rows)
    model_mean = float(np.mean(model_brier))
    raw_mean = float(np.mean(raw_brier))
    baseline_mean = float(np.mean(baseline_brier))
    names = ("target_first", "stop_first", "neither")
    class_summary = {
        name: {
            "observed_frequency": float(class_actual[j] / count),
            "mean_predicted_probability": float(class_predicted[j] / count),
            "mean_raw_predicted_probability": float(class_raw_predicted[j] / count),
            "mean_baseline_probability": float(class_baseline[j] / count)
        }
        for j, name in enumerate(names)
    }
    return {
        "observations": count,
        "multiclass_brier_score": model_mean,
        "raw_multiclass_brier_score": raw_mean,
        "baseline_multiclass_brier_score": baseline_mean,
        "brier_skill_score": (float(1.0 - model_mean / baseline_mean)
                              if baseline_mean > 0 else None),
        "class_summary": class_summary,
        "rows": rows,
        "drift_convention": drift_convention,
        "periods_per_year": periods_per_year,
        "step_year_fraction": dt,
        "horizon_years": horizon * dt,
        "estimation_window": estimation_window,
        "calibration_window": calibration_window,
        "min_calibration_observations": min_calibration_observations,
        "min_calibration_improvement": min_calibration_improvement,
        "first_forecast_index": first_origin,
        "baseline_method": "rolling empirical frequencies of fully observed prior barrier outcomes",
        "calibration_method": "causal convex blend fitted on matured prior out-of-sample forecasts; minimum-improvement gate and baseline-only fallback",
        "warning": "Close-only diagnostic; not a profitability test. Same-bar OHLC order, costs and slippage are not modeled."
    }
