"""Deterministic specialist libraries; these are not AI agents."""
from .data_quality import validate_price_series, validate_dated_prices, audit_dated_prices
from .volatility import volatility_profile
from .shock_scenarios import apply_price_shock
from .numerical_stability import safe_gbm_paths, iter_gbm_path_chunks
__all__ = ["validate_price_series", "validate_dated_prices", "audit_dated_prices", "volatility_profile",
           "apply_price_shock", "safe_gbm_paths", "iter_gbm_path_chunks"]
