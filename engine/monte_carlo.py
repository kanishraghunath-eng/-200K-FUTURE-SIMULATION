"""Reproducible GBM simulation with optional memory-bounded summaries."""
import math
import numpy as np
from .specialists import validate_price_series
from .specialists.numerical_stability import safe_gbm_paths, iter_gbm_path_chunks


def simulate_price_paths(prices, steps, paths=200_000, drift_mode="historical", seed=7,
                         chunk_size=10_000, periods_per_year=252, return_paths=True,
                         entry=None, target=None, stop=None, drift_convention="corrected"):
    """Historical drift is mean log return; legacy reproduces the v2.2.0 convention."""
    check = validate_price_series(prices)
    values = np.asarray(prices, dtype=float)
    if not isinstance(steps, int) or steps < 1:
        raise ValueError("steps must be an integer >= 1")
    if not isinstance(paths, int) or paths < 1:
        raise ValueError("paths must be a positive integer")
    if drift_mode not in {"historical", "zero"}:
        raise ValueError("drift_mode must be 'historical' or 'zero'")
    if drift_convention not in {"corrected", "legacy"}:
        raise ValueError("drift_convention must be 'corrected' or 'legacy'")
    if not isinstance(periods_per_year, int) or periods_per_year <= 0:
        raise ValueError("periods_per_year must be a positive integer")
    barriers = any(x is not None for x in (entry, target, stop))
    if barriers and (entry is None or target is None or stop is None or not (0 < stop < entry < target)):
        raise ValueError("provide all barriers satisfying 0 < stop < entry < target")
    rets = np.diff(np.log(values))
    mean_log = float(np.mean(rets) * periods_per_year)
    sigma = float(np.std(rets, ddof=1) * math.sqrt(periods_per_year))
    if drift_mode == "zero":
        mu, annualized_drift = 0.0, 0.0
    else:
        annualized_drift = mean_log
        mu = mean_log + (0.5 * sigma ** 2 if drift_convention == "corrected" else 0.0)
    simulated_log = mu - 0.5 * sigma ** 2
    meta = {"paths": paths, "steps": steps, "drift_mode": drift_mode,
            "annualized_drift": annualized_drift, "annualized_volatility": sigma,
            "seed": seed, "input_quality": check,
            "model": "GBM log-space; equally spaced steps", "numerically_saturated": False,
            "drift_definition": "annualized mean log return (historical); arithmetic GBM drift (zero)",
            "drift_convention": drift_convention, "annualized_arithmetic_drift": mu,
            "simulated_log_drift": simulated_log}
    if return_paths:
        result = safe_gbm_paths(float(values[-1]), mu, sigma, steps, paths, seed, chunk_size)
        meta["numerically_saturated"] = result["numerically_saturated"]
        return {"paths": result["paths"], "metadata": meta}
    terminal = np.empty(paths, dtype=np.float64)
    counts = {"target": 0, "stop": 0, "neither": 0, "ambiguous": 0}
    for begin, chunk, flag in iter_gbm_path_chunks(float(values[-1]), mu, sigma, steps, paths, seed, chunk_size):
        meta["numerically_saturated"] |= flag
        terminal[begin:begin + len(chunk)] = chunk[:, -1]
        if barriers:
            future = chunk[:, 1:]
            ht, hs = future >= target, future <= stop
            at, ass = ht.any(axis=1), hs.any(axis=1)
            ft = np.where(at, ht.argmax(axis=1), steps + 1)
            fs = np.where(ass, hs.argmax(axis=1), steps + 1)
            ambiguous = at & ass & (ft == fs)
            counts["ambiguous"] += int(ambiguous.sum())
            counts["target"] += int(((ft < fs) & ~ambiguous).sum())
            counts["stop"] += int(((fs < ft) & ~ambiguous).sum())
            counts["neither"] += int((~at & ~ass).sum())
    summary = {"terminal_quantiles": {str(q): float(np.quantile(terminal, q))
                                      for q in (0.05, 0.25, 0.5, 0.75, 0.95)},
               "terminal_mean": float(terminal.mean()), "path_count": paths,
               "storage_mode": "streamed_summary"}
    if barriers:
        summary.update({"target_first_probability": counts["target"]/paths,
                        "stop_first_probability": counts["stop"]/paths,
                        "neither_probability": counts["neither"]/paths,
                        "same_step_ambiguous_probability": counts["ambiguous"]/paths})
    return {"paths": None, "metadata": meta, "summary": summary}


def barrier_probabilities(path_matrix, entry, target, stop):
    p = np.asarray(path_matrix, dtype=float)
    if p.ndim != 2 or p.shape[1] < 2 or not np.isfinite(p).all() or (p <= 0).any():
        raise ValueError("path_matrix must be a finite positive 2D array with future steps")
    if not (0 < stop < entry < target):
        raise ValueError("require 0 < stop < entry < target")
    future = p[:, 1:]
    ht, hs = future >= target, future <= stop
    at, ass = ht.any(axis=1), hs.any(axis=1)
    ft = np.where(at, ht.argmax(axis=1), future.shape[1] + 1)
    fs = np.where(ass, hs.argmax(axis=1), future.shape[1] + 1)
    ambiguous = at & ass & (ft == fs)
    target_first, stop_first = (ft < fs) & ~ambiguous, (fs < ft) & ~ambiguous
    neither = ~at & ~ass
    terminal = future[:, -1]
    return {"target_first_probability": float(target_first.mean()),
            "stop_first_probability": float(stop_first.mean()),
            "neither_probability": float(neither.mean()),
            "same_step_ambiguous_probability": float(ambiguous.mean()),
            "terminal_quantiles": {str(q): float(np.quantile(terminal, q)) for q in (0.05, .25, .5, .75, .95)},
            "terminal_mean": float(terminal.mean()), "path_count": int(p.shape[0])}
