"""The demo seed script is what a fresh clone runs first, so it has to work on
an empty database and stay safe to re-run."""
from __future__ import annotations

import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "seed_demo.py"


@pytest.fixture
def seed_module(tmp_path, monkeypatch):
    db_path = tmp_path / "seed.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setattr(sys, "argv", ["seed_demo.py"])

    spec = importlib.util.spec_from_file_location("seed_demo_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, db_path


def query(db_path, sql, *params):
    with sqlite3.connect(db_path) as connection:
        return connection.execute(sql, params).fetchall()


def test_seeding_an_empty_database_succeeds(seed_module):
    module, db_path = seed_module

    module.main()

    assert query(db_path, "SELECT COUNT(*) FROM users")[0][0] == 3

    shipments = dict(query(db_path, "SELECT status, COUNT(*) FROM shipments GROUP BY status"))
    assert shipments == {
        "pending": 1,
        "assigned": 1,
        "picked_up": 2,
        "in_transit": 1,
        "out_for_delivery": 1,
        "delivered": 1,
        "delivery_failed": 1,
    }


def test_assigned_target_does_not_walk_the_transport_chain(seed_module):
    module, db_path = seed_module

    module.main()

    (shipment_id,) = query(
        db_path,
        "SELECT id FROM shipments WHERE recipient_name = ?",
        "Wong Siu Ming",
    )[0]
    walked = query(
        db_path,
        "SELECT status FROM shipment_events WHERE shipment_id = ? "
        "AND status IN ('picked_up', 'in_transit', 'out_for_delivery')",
        shipment_id,
    )
    assert walked == []


def test_seeding_twice_does_not_duplicate_anything(seed_module):
    module, db_path = seed_module

    module.main()
    first = query(db_path, "SELECT tracking_number FROM shipments ORDER BY tracking_number")

    module.main()
    second = query(db_path, "SELECT tracking_number FROM shipments ORDER BY tracking_number")

    assert first == second
    assert query(db_path, "SELECT COUNT(*) FROM users")[0][0] == 3
    assert query(db_path, "SELECT COUNT(*) FROM customers")[0][0] == 3


def test_unsupported_target_is_rejected(seed_module):
    module, _ = seed_module

    with pytest.raises(ValueError, match="unsupported seed target"):
        module.make_shipment(
            customer=None, actor=None, recipient="nobody", phone="60000000",
            destination="nowhere", driver=None, target="teleported",
        )
