"""Numerically stable GBM chunks with an explicit year fraction per step.

Each log increment is (mu - volatility**2 / 2) * dt + sigma * sqrt(dt) * Z.
When omitted, step_year_fraction preserves the historical equally-spaced
one-year horizon (dt=1/steps) for direct primitive callers.
"""
import math
import numpy as np


def iter_gbm_path_chunks(start_price, drift, volatility, steps, paths=200_000,
                         seed=7, chunk_size=10_000, step_year_fraction=None):
    if any(not math.isfinite(float(x)) for x in (start_price, drift, volatility)):
        raise ValueError("start_price, drift and volatility must be finite")
    if start_price <= 0 or volatility < 0:
        raise ValueError("start_price must be > 0 and volatility >= 0")
    if not isinstance(steps, int) or steps < 1:
        raise ValueError("steps must be an integer >= 1")
    if not isinstance(paths, int) or paths < 1 or not isinstance(chunk_size, int) or chunk_size < 1:
        raise ValueError("paths and chunk_size must be positive integers")
    if step_year_fraction is None:
        dt = 1.0 / steps
    else:
        try:
            dt = float(step_year_fraction)
        except (TypeError, ValueError):
            raise ValueError("step_year_fraction must be a finite positive number")
        if not math.isfinite(dt) or dt <= 0:
            raise ValueError("step_year_fraction must be a finite positive number")
    rng = np.random.default_rng(seed)
    with np.errstate(over="ignore", invalid="ignore"):
        drift_step = (np.float64(drift) - 0.5 * np.float64(volatility)**2) * dt
        vol_step = np.float64(volatility) * math.sqrt(dt)
    if not np.isfinite(drift_step) or not np.isfinite(vol_step):
        raise ValueError("drift/volatility are too extreme")
    lo, hi = math.log(np.finfo(np.float64).tiny), math.log(np.finfo(np.float64).max) - 2
    for begin in range(0, paths, chunk_size):
        count = min(chunk_size, paths - begin)
        z = rng.standard_normal((count, steps))
        with np.errstate(over="ignore", invalid="ignore"):
            logs = math.log(start_price) + np.cumsum(drift_step + vol_step*z, axis=1)
        saturated = not np.isfinite(logs).all() or bool(np.any((logs < lo) | (logs > hi)))
        logs = np.clip(np.nan_to_num(logs, nan=0.0, posinf=hi, neginf=lo), lo, hi)
        chunk = np.empty((count, steps + 1), dtype=np.float64)
        chunk[:, 0] = start_price
        chunk[:, 1:] = np.exp(logs)
        if not np.isfinite(chunk).all() or (chunk <= 0).any():
            raise FloatingPointError("simulation produced invalid prices")
        yield begin, chunk, saturated


def safe_gbm_paths(start_price, drift, volatility, steps, paths=200_000, seed=7,
                   chunk_size=10_000, step_year_fraction=None):
    """Compatibility API returning a full matrix; use iterator for streamed summaries."""
    out = np.empty((paths, steps + 1), dtype=np.float64)
    saturated = False
    for begin, chunk, flag in iter_gbm_path_chunks(
            start_price, drift, volatility, steps, paths, seed, chunk_size,
            step_year_fraction):
        out[begin:begin + len(chunk)] = chunk
        saturated = saturated or flag
    return {"paths": out, "numerically_saturated": saturated,
            "model": "GBM log-space; explicit year fraction per step", "seed": seed}
