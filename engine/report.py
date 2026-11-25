"""Small dependency-free report formatter for simulation outputs."""
import json


def build_simulation_report(simulation, risk_metrics=None, data_status=None):
    metadata = simulation.get("metadata", {})
    summary = simulation.get("summary", {})
    report = {
        "data_status": data_status or metadata.get("input_quality", "not supplied"),
        "model": metadata.get("model", "not specified"),
        "assumptions": {key: metadata.get(key) for key in
                        ("paths", "steps", "seed", "drift_mode",
                         "annualized_drift", "annualized_volatility")},
        "simulation_summary": summary,
        "historical_risk": risk_metrics or {},
        "limitations": [
            "Scenario outputs are conditional on model assumptions, not predictions or guarantees.",
            "Monte Carlo path count does not remove model, data, or parameter-estimation error.",
            "Corporate-action adjustment and market-calendar correctness require source-level review."
        ],
        "conclusion": "EDUCATIONAL_SCENARIO_ANALYSIS_ONLY"
    }
    return report


def report_to_json(report, indent=2):
    return json.dumps(report, indent=indent, sort_keys=True, allow_nan=False)
