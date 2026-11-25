"""Simple close-only walk-forward barrier diagnostics; not a trading strategy."""
import numpy as np
from .monte_carlo import simulate_price_paths, barrier_probabilities


def walk_forward_barrier_diagnostic(prices, entry_offset=0.0, target_pct=0.03, stop_pct=0.02,
                                    horizon=10, min_train=60, paths=5000, seed=7, drift_convention="corrected"):
    p = np.asarray(prices, dtype=float)
    if p.ndim != 1 or len(p) < min_train + horizon + 3 or not np.isfinite(p).all() or (p <= 0).any():
        raise ValueError("insufficient or invalid prices for walk-forward diagnostic")
    if target_pct <= 0 or not 0 < stop_pct < 1 or horizon < 1:
        raise ValueError("invalid barrier or horizon settings")
    rows=[]; brier=[]
    for i in range(min_train, len(p)-horizon):
        train=p[:i+1]
        entry=float(train[-1]*(1+entry_offset))
        target=entry*(1+target_pct); stop=entry*(1-stop_pct)
        sim=simulate_price_paths(train,horizon,paths=paths,seed=seed+i,drift_mode="historical",
                                 drift_convention=drift_convention)
        pred=barrier_probabilities(sim["paths"],entry,target,stop)
        future=p[i+1:i+1+horizon]
        t=np.where(future>=target)[0]; s=np.where(future<=stop)[0]
        actual=0 if len(t) and (not len(s) or t[0]<s[0]) else (1 if len(s) else 2)
        probs=[pred["target_first_probability"],pred["stop_first_probability"],pred["neither_probability"]]
        onehot=[1.0 if actual==j else 0.0 for j in range(3)]
        brier.append(sum((probs[j]-onehot[j])**2 for j in range(3)))
        rows.append({"index":i,"actual_class":("target_first" if actual==0 else "stop_first" if actual==1 else "neither"),"predicted":probs})
    return {"observations":len(rows),"multiclass_brier_score":float(np.mean(brier)),"rows":rows,
            "drift_convention": drift_convention,
            "warning":"Close-only diagnostic; not a profitability test. Same-bar OHLC order and costs are not modeled."}
