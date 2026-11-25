"""CSV input helpers. Uses only the Python standard library."""
import csv
from pathlib import Path
from .specialists import validate_dated_prices


def load_price_csv(path, currency=None, expected_interval=None,
                   corporate_actions_reviewed=False):
    """Load a CSV with required 'date' and 'close' columns and validate it."""
    source = Path(path)
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or not {"date", "close"}.issubset(set(reader.fieldnames)):
            raise ValueError("CSV must contain date and close columns")
        rows = list(reader)
    validation = validate_dated_prices(
        rows, currency=currency, expected_interval=expected_interval,
        corporate_actions_reviewed=corporate_actions_reviewed)
    return {"dates": [row["date"] for row in rows],
            "prices": [float(row["close"]) for row in rows],
            "validation": validation,
            "source": str(source)}
