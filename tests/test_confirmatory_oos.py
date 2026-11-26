import unittest
from unittest.mock import patch

from scripts.run_confirmatory_oos import run_confirmatory_manifest


def base_item(**overrides):
    item = {
        "instrument_id": "TEST", "asset_class": "equity_index",
        "source": "fixture", "currency": "USD", "interval": "daily",
        "timezone": "America/New_York", "calendar": "NYSE",
        "adjustment_basis": "not_applicable",
        "corporate_actions_applicability": "not_applicable",
        "provider": "yahoo", "price_field": "close",
        "confirmatory_candidate": True,
    }
    item.update(overrides)
    return item


def payload(item):
    return {
        "protocol_id": "fixture-v1", "status": "preregistered_waiting_for_future_holdout",
        "freeze_date": "2026-11-26", "holdout_start": "2026-11-27",
        "acceptance_criteria": {"alpha": 0.05},
        "datasets": [item], "blocked_candidates": [],
    }


def evaluated(timestamps, rows, **overrides):
    result = {
        "status": "evaluated", "provider": "fixture",
        "source_sha256": "a" * 64, "data_sha256": "b" * 64,
        "audit": {"valid": True},
        "corporate_action_audit": {"status": "not_applicable"},
        "observation_timestamps": timestamps,
        "oos_diagnostic": {"rows": rows},
    }
    result.update(overrides)
    return result


class ConfirmatoryOOSTests(unittest.TestCase):
    def test_requires_holdout_strictly_after_freeze_date(self):
        manifest = payload(base_item())
        manifest["holdout_start"] = manifest["freeze_date"]
        with self.assertRaisesRegex(ValueError, "strictly later"):
            run_confirmatory_manifest(manifest)

    def test_pre_freeze_forecasts_are_not_scored_and_future_holdout_waits(self):
        rows = [
            {"index": 0, "brier_score": 0.3, "baseline_brier_score": 0.5},
            {"index": 1, "brier_score": 0.3, "baseline_brier_score": 0.5},
        ]
        data = evaluated(
            ["2026-11-26T00:00:00+00:00", "2026-11-27T00:00:00+00:00"],
            rows,
        )
        with patch("scripts.run_confirmatory_oos.evaluate_dataset", return_value=data):
            report = run_confirmatory_manifest(
                payload(base_item()), paths=100, replicates=200,
                minimum_forecasts=2,
            )
        self.assertEqual(report["status"], "awaiting_future_holdout")
        self.assertEqual(report["awaiting_future_holdout"][0]["holdout_forecasts_available"], 1)
        self.assertEqual(report["results"], [])

    def test_unmatched_corporate_actions_block_the_confirmatory_family(self):
        item = base_item(
            instrument_id="ETF.TEST", asset_class="etf",
            adjustment_basis="provider_adjusted",
            corporate_actions_provider="eodhd",
        )
        data = evaluated(
            ["2026-11-27T00:00:00+00:00"],
            [{"index": 0, "brier_score": 0.3, "baseline_brier_score": 0.5}],
            corporate_action_audit={"status": "unavailable"},
        )
        with patch("scripts.run_confirmatory_oos.evaluate_dataset", return_value=data):
            report = run_confirmatory_manifest(payload(item), minimum_forecasts=1)
        self.assertEqual(report["status"], "blocked_preconditions")
        self.assertIn("corporate_action_reconciliation:unavailable",
                      report["precondition_failures"][0]["blockers"])

    def test_missing_dataset_hash_blocks_confirmation(self):
        data = evaluated(["2026-11-27"], [], source_sha256=None)
        with patch("scripts.run_confirmatory_oos.evaluate_dataset", return_value=data):
            report = run_confirmatory_manifest(payload(base_item()))
        self.assertEqual(report["status"], "blocked_preconditions")
        self.assertIn("missing_source_or_canonical_hash",
                      report["precondition_failures"][0]["blockers"])


if __name__ == "__main__":
    unittest.main()
