"""Chunked, reproducible geometric-Brownian-motion scenario simulation."""
import math
import numpy as np
from .specialists import validate_price_series, safe_gbm_paths


def simulate_price_paths(prices, steps, paths=200_000, drift_mode="historical", seed=7,
                         chunk_size=10_000, periods_per_year=252):
    """Simulate equally spaced future close-price paths from historical prices."""
    check = validate_price_series(prices)
    values = np.asarray(prices, dtype=float)
    if not isinstance(steps, int) or steps < 1:
        raise ValueError("steps must be an integer >= 1")
    if not isinstance(paths, int) or paths < 1:
        raise ValueError("paths must be a positive integer")
    if drift_mode not in {"historical", "zero"}:
        raise ValueError("drift_mode must be 'historical' or 'zero'")
    if not isinstance(periods_per_year, int) or periods_per_year <= 0:
        raise ValueError("periods_per_year must be a positive integer")
    log_returns = np.diff(np.log(values))
    mu = float(np.mean(log_returns) * periods_per_year) if drift_mode == "historical" else 0.0
    sigma = float(np.std(log_returns, ddof=1) * math.sqrt(periods_per_year))
    result = safe_gbm_paths(float(values[-1]), mu, sigma, steps, paths, seed, chunk_size)
    arr = result["paths"]
    return {"paths": arr, "metadata": {"paths": paths, "steps": steps,
            "drift_mode": drift_mode, "annualized_drift": mu,
            "annualized_volatility": sigma, "seed": seed,
            "input_quality": check, "model": result["model"],
            "numerically_saturated": result["numerically_saturated"]}}


def barrier_probabilities(path_matrix, entry, target, stop):
    """Long-only first-hit probabilities; same-step dual hits are ambiguous."""
    p = np.asarray(path_matrix, dtype=float)
    if p.ndim != 2 or p.shape[1] < 2 or not np.isfinite(p).all() or (p <= 0).any():
        raise ValueError("path_matrix must be a finite positive 2D array with future steps")
    if not (0 < stop < entry < target):
        raise ValueError("require 0 < stop < entry < target")
    future = p[:, 1:]
    hit_t = future >= target
    hit_s = future <= stop
    any_t = hit_t.any(axis=1); any_s = hit_s.any(axis=1)
    first_t = np.where(any_t, hit_t.argmax(axis=1), future.shape[1] + 1)
    first_s = np.where(any_s, hit_s.argmax(axis=1), future.shape[1] + 1)
    both_same = any_t & any_s & (first_t == first_s)
    target_first = (first_t < first_s) & ~both_same
    stop_first = (first_s < first_t) & ~both_same
    neither = ~any_t & ~any_s
    terminal = future[:, -1]
    return {"target_first_probability": float(target_first.mean()),
            "stop_first_probability": float(stop_first.mean()),
            "neither_probability": float(neither.mean()),
            "same_step_ambiguous_probability": float(both_same.mean()),
            "terminal_quantiles": {str(q): float(np.quantile(terminal, q)) for q in (0.05, 0.25, 0.5, 0.75, 0.95)},
            "terminal_mean": float(terminal.mean()), "path_count": int(p.shape[0])}
