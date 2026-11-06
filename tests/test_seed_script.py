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
    monkeypatch.setenv("SECRET_KEY", "seed-testing-only-secret")
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
        "pending": 2,
        "assigned": 5,
        "picked_up": 2,
        "in_transit": 1,
        "out_for_delivery": 1,
        "delivered": 3,
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
    assert query(db_path, "SELECT COUNT(*) FROM customers")[0][0] == 4


def test_unsupported_target_is_rejected(seed_module):
    module, _ = seed_module

    with pytest.raises(ValueError, match="unsupported seed target"):
        module.make_shipment(
            customer=None, actor=None, recipient="nobody", phone="60000000",
            destination="nowhere", driver=None, target="teleported",
        )


def test_report_demo_dates_metrics_and_filters(seed_module):
    from app.extensions import db
    from app.models import Shipment, User
    from app.services.delivery_monitoring import delivery_metrics, overdue_conditions

    module, db_path = seed_module
    module.main()
    app = module.create_app()
    with app.app_context():
        customer = db.session.scalar(db.select(module.Customer).where(
            module.Customer.name == 'DEMO Report Acceptance'))
        rows = db.session.scalars(db.select(Shipment).where(Shipment.customer_id == customer.id)).all()
        by_name = {s.recipient_name:s for s in rows}
        today = by_name['DEMO TODAY-A'].expected_delivery_date
        assert by_name['DEMO LATE-A'].expected_delivery_date == today - module.timedelta(days=1)
        assert by_name['DEMO OLD-LATE-A'].created_at.date() == today - module.timedelta(days=7)
        assert by_name['DEMO FUTURE'].expected_delivery_date == today + module.timedelta(days=1)
        assert delivery_metrics((Shipment.customer_id == customer.id,), today=today) == {
            'overdue':3, 'on_time':1, 'measured_deliveries':2, 'on_time_rate':50.0}
        driver = db.session.scalar(db.select(User).where(User.email == 'driver@example.com'))
        result = db.session.scalars(db.select(Shipment).where(
            Shipment.customer_id == customer.id, Shipment.driver_id == driver.id,
            Shipment.status == 'assigned', Shipment.created_at >= module.datetime.combine(
                today, module.datetime.min.time()), *overdue_conditions(today))).all()
        assert [s.recipient_name for s in result] == ['DEMO LATE-A']


def test_report_demo_rerun_preserves_existing_snapshots(seed_module):
    module, db_path = seed_module
    module.main()
    # The local acceptance fixtures have dated tracking numbers; adopt them as-is.
    with sqlite3.connect(db_path) as connection:
        connection.execute("UPDATE shipments SET tracking_number='DEMO-RPT-OLD-LOCAL', status='pending' "
                           "WHERE tracking_number='DEMO-RPT-LATE-A'")
    original = query(db_path, 'SELECT * FROM shipments ORDER BY id')
    original_events = query(db_path, 'SELECT * FROM shipment_events ORDER BY id')
    app = module.create_app()
    with app.app_context():
        users = module.db.session.scalars(module.db.select(module.User).order_by(module.User.id)).all()
        staff = next(u for u in users if u.role == 'staff')
        drivers = [u for u in users if u.role == 'driver']
        assert module.seed_report_shipments(
            staff, drivers, now=module.datetime.now(module.timezone.utc) + module.timedelta(days=1)) == []
    assert query(db_path, 'SELECT * FROM shipments ORDER BY id') == original
    assert query(db_path, 'SELECT * FROM shipment_events ORDER BY id') == original_events
