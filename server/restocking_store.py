"""
Persistence for submitted restocking orders.

This is the ONLY place in the app that writes data back to disk — every
other dataset in server/data/ is read-only mock data loaded once via
mock_data.py. Restocking orders must survive a backend restart, so they get
their own self-contained read-modify-write helper instead of spreading file
I/O logic into main.py or mock_data.py.
"""
import json
from pathlib import Path

RESTOCKING_ORDERS_FILE = Path(__file__).parent / "data" / "restocking_orders.json"


def read_all() -> list:
    """Read persisted restocking orders, creating the file if it doesn't exist yet."""
    if not RESTOCKING_ORDERS_FILE.exists():
        RESTOCKING_ORDERS_FILE.write_text("[]")
        return []
    with open(RESTOCKING_ORDERS_FILE, "r") as f:
        return json.load(f)


def write_all(orders: list) -> None:
    """Overwrite the file with the full current list of restocking orders."""
    with open(RESTOCKING_ORDERS_FILE, "w") as f:
        json.dump(orders, f, indent=2)
