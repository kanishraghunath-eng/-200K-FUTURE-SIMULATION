import unittest
import numpy as np
from engine.specialists.data_quality import validate_price_series
from engine.specialists.volatility import volatility_profile
from engine.specialists.shock_scenarios import apply_price_shock
from engine.specialists.numerical_stability import safe_gbm_paths


class SpecialistTests(unittest.TestCase):
    def test_data_quality_valid_and_invalid(self):
        self.assertTrue(validate_price_series([100, 101, 99])["valid"])
        with self.assertRaises(ValueError):
            validate_price_series([100, float('nan'), 99])
        with self.assertRaises(ValueError):
            validate_price_series([100, 900, 99])

    def test_volatility_flat_series(self):
        self.assertEqual(volatility_profile([10, 10, 10])["annualized_volatility"], 0)

    def test_shocks(self):
        self.assertEqual(apply_price_shock([100, 110, 120], -10, 1), [100, 99, 108])
        with self.assertRaises(ValueError):
            apply_price_shock([100], -100)

    def test_gbm_reproducible_and_positive(self):
        a = safe_gbm_paths(100, 0.05, 0.2, 20, paths=2000, seed=3)
        b = safe_gbm_paths(100, 0.05, 0.2, 20, paths=2000, seed=3)
        self.assertTrue(np.array_equal(a['paths'], b['paths']))
        self.assertTrue(np.isfinite(a['paths']).all())
        self.assertTrue((a['paths'] > 0).all())

    def test_gbm_extreme_volatility_is_finite(self):
        result = safe_gbm_paths(100, 0, 100, 12, paths=1000, seed=4)
        self.assertTrue(np.isfinite(result['paths']).all())
        self.assertTrue((result['paths'] > 0).all())

    def test_invalid_gbm_parameters(self):
        with self.assertRaises(ValueError):
            safe_gbm_paths(0, 0, 0.2, 10)
        with self.assertRaises(ValueError):
            safe_gbm_paths(100, 0, -1, 10)
        with self.assertRaises(ValueError):
            safe_gbm_paths(100, 0, 1e308, 10)
        with self.assertRaises(ValueError):
            safe_gbm_paths(100, 0, 0.2, 0)

    def test_specialists_reject_malformed_inputs(self):
        with self.assertRaises(ValueError):
            validate_price_series([100, "bad", 102])
        with self.assertRaises(ValueError):
            volatility_profile([100, float("inf"), 102])
        with self.assertRaises(ValueError):
            apply_price_shock([100, 101], float("nan"))

    def test_gbm_full_default_path_count_shape(self):
        result = safe_gbm_paths(100, 0.01, 0.15, 3, paths=200_000, seed=9, chunk_size=25_000)
        self.assertEqual(result["paths"].shape, (200_000, 4))
        self.assertTrue(np.isfinite(result["paths"]).all())
        self.assertTrue((result["paths"] > 0).all())


if __name__ == '__main__':
    unittest.main()
