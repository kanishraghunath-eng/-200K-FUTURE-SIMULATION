import unittest
import numpy as np
from engine.monte_carlo import simulate_price_paths, barrier_probabilities
from engine.risk_metrics import historical_risk_metrics
from engine.backtest import walk_forward_barrier_diagnostic
from engine.specialists import validate_price_series, volatility_profile, apply_price_shock


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.prices = [100 + i*0.15 + np.sin(i/4) for i in range(120)]

    def test_default_path_count_and_shape(self):
        out = simulate_price_paths(self.prices, 5, paths=200_000, seed=11)
        self.assertEqual(out['paths'].shape, (200_000, 6))
        self.assertTrue(np.isfinite(out['paths']).all())

    def test_reproducibility(self):
        a = simulate_price_paths(self.prices, 4, paths=100, seed=5)['paths']
        b = simulate_price_paths(self.prices, 4, paths=100, seed=5)['paths']
        np.testing.assert_array_equal(a, b)

    def test_barrier_probabilities_sum(self):
        paths = simulate_price_paths(self.prices, 5, paths=2000)['paths']
        r = barrier_probabilities(paths, float(self.prices[-1]), float(self.prices[-1])*1.05, float(self.prices[-1])*.95)
        total = sum(r[k] for k in ('target_first_probability', 'stop_first_probability', 'neither_probability', 'same_step_ambiguous_probability'))
        self.assertAlmostEqual(total, 1.0, places=10)

    def test_risk_metrics(self):
        r = historical_risk_metrics(self.prices)
        self.assertIn('max_drawdown', r)

    def test_specialists(self):
        self.assertTrue(validate_price_series(self.prices)['valid'])
        self.assertGreater(volatility_profile(self.prices)['annualized_volatility'], 0)
        self.assertAlmostEqual(apply_price_shock([100, 101], -10)[0], 90)

    def test_walk_forward_diagnostic_runs(self):
        r = walk_forward_barrier_diagnostic(self.prices, horizon=3, min_train=80, paths=100)
        self.assertGreater(r["observations"], 0)
        self.assertGreaterEqual(r["multiclass_brier_score"], 0)

    def test_invalid_series_rejected(self):
        with self.assertRaises(ValueError):
            validate_price_series([1, 0, 2])


if __name__ == '__main__':
    unittest.main()
