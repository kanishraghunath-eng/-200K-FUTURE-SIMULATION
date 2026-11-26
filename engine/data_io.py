"""CSV input helpers. Uses only the Python standard library."""
import csv
from pathlib import Path
from .specialists import validate_dated_prices


def load_price_csv(path, currency=None, expected_interval=None,
                   corporate_actions_reviewed=False, collect_all_errors=False,
                   max_abs_return=5.0):
    """Load date,close CSV. In audit mode invalid data is returned with prices=None."""
    source = Path(path)
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not {"date", "close"}.issubset(set(reader.fieldnames)):
            raise ValueError("CSV must contain date and close columns")
        rows = list(reader)
    validation = validate_dated_prices(
        rows, currency=currency, expected_interval=expected_interval,
        corporate_actions_reviewed=corporate_actions_reviewed,
        collect_all_errors=collect_all_errors, max_abs_return=max_abs_return)
    result = {"dates": [row.get("date") for row in rows],
              "prices": None if not validation["valid"] else [float(row["close"]) for row in rows],
              "validation": validation, "source": str(source)}
    return result
