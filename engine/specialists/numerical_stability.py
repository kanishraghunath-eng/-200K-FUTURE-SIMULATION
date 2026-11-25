"""Numerically stable GBM path generator using log-space and bounded chunks."""
import math
import numpy as np


def safe_gbm_paths(start_price, drift, volatility, steps, paths=200_000, seed=7, chunk_size=10_000):
    vals = (start_price, drift, volatility)
    if any(not math.isfinite(float(x)) for x in vals):
        raise ValueError("start_price, drift and volatility must be finite")
    if start_price <= 0 or volatility < 0:
        raise ValueError("start_price must be > 0 and volatility >= 0")
    if not isinstance(steps, int) or steps < 1:
        raise ValueError("steps must be an integer >= 1")
    if not isinstance(paths, int) or paths < 1 or not isinstance(chunk_size, int) or chunk_size < 1:
        raise ValueError("paths and chunk_size must be positive integers")
    rng = np.random.default_rng(seed)
    out = np.empty((paths, steps + 1), dtype=np.float64)
    out[:, 0] = start_price
    dt = 1.0 / steps
    with np.errstate(over="ignore", invalid="ignore"):
        variance_term = np.float64(volatility) * np.float64(volatility)
        drift_step = (np.float64(drift) - 0.5 * variance_term) * dt
        vol_step = np.float64(volatility) * math.sqrt(dt)
    if not np.isfinite(drift_step) or not np.isfinite(vol_step):
        raise ValueError("drift/volatility are too extreme for stable GBM coefficients")
    lo, hi = math.log(np.finfo(np.float64).tiny), math.log(np.finfo(np.float64).max) - 2
    saturated = False
    for begin in range(0, paths, chunk_size):
        end = min(begin + chunk_size, paths)
        z = rng.standard_normal((end - begin, steps))
        with np.errstate(over="ignore", invalid="ignore"):
            increments = drift_step + vol_step * z
            log_path = math.log(start_price) + np.cumsum(increments, axis=1)
        if not np.isfinite(log_path).all():
            saturated = True
            log_path = np.nan_to_num(log_path, nan=0.0, posinf=hi, neginf=lo)
        if np.any((log_path < lo) | (log_path > hi)):
            saturated = True
            log_path = np.clip(log_path, lo, hi)
        out[begin:end, 1:] = np.exp(log_path)
    if not np.isfinite(out).all() or (out <= 0).any():
        raise FloatingPointError("simulation produced invalid prices")
    return {"paths": out, "numerically_saturated": saturated,
            "model": "GBM log-space; equally spaced steps", "seed": seed}
