"""Deterministic specialist analysis modules; these are libraries, not agents."""
from .data_quality import validate_price_series
from .volatility import volatility_profile
from .shock_scenarios import apply_price_shock
from .numerical_stability import safe_gbm_paths

__all__ = ["validate_price_series", "volatility_profile", "apply_price_shock", "safe_gbm_paths"]
