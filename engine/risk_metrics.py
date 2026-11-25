"""Descriptive historical risk metrics; not a prediction of future risk."""
import numpy as np


def historical_risk_metrics(prices, periods_per_year=252, risk_free_rate=0.0, confidence=0.95):
    p = np.asarray(prices, dtype=float)
    if p.ndim != 1 or len(p) < 3 or not np.isfinite(p).all() or (p <= 0).any():
        raise ValueError("prices must be a 1D sequence of at least three finite positive values")
    if not 0 < confidence < 1 or periods_per_year <= 0:
        raise ValueError("invalid confidence or periods_per_year")
    r = p[1:] / p[:-1] - 1
    vol = float(np.std(r, ddof=1) * np.sqrt(periods_per_year))
    q = float(np.quantile(r, 1-confidence))
    tail = r[r <= q]
    peaks = np.maximum.accumulate(p)
    dd = p / peaks - 1
    sharpe = float((np.mean(r)*periods_per_year-risk_free_rate)/(np.std(r, ddof=1)*np.sqrt(periods_per_year))) if np.std(r, ddof=1) else None
    return {"annualized_volatility": vol, "historical_var_return": q,
            "historical_expected_shortfall_return": float(tail.mean()) if len(tail) else q,
            "max_drawdown": float(dd.min()), "annualized_sharpe": sharpe,
            "observations": int(len(p))}
