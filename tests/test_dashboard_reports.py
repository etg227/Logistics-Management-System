"""Integration regressions for dashboard analytics and CSV report access."""
import csv
from datetime import datetime, timedelta, timezone
from io import StringIO
from uuid import uuid4

import pytest
from app.extensions import db
from app.models import Customer, Shipment, ShipmentEvent, User
from app.models.shipment import (DELIVERED, DELIVERY_FAILED, RETURNED, ASSIGNED, CANCELLED)
from app.services.analytics import dashboard_data, report_summary, shipment_conditions


def login(client, role="admin"):
    return client.post("/login", data={"email": f"{role}@example.com",
                                       "password": "test-password-123"}, follow_redirects=True)


def add_shipment(app, *, status="pending", recipient="Report Receiver",
                 driver=False, created_at=None, failed_events=0, customer_name="Report Customer"):
    with app.app_context():
        staff = db.session.scalar(db.select(User).where(User.role == "staff"))
        delivery_driver = db.session.scalar(db.select(User).where(User.role == "driver"))
        customer = Customer(name=customer_name, phone="12345678", address="Demo Street")
        db.session.add(customer)
        db.session.flush()
        row = Shipment(
            tracking_number="CF-REPORT-" + uuid4().hex[:16].upper(),
            customer_id=customer.id, created_by_id=staff.id,
            driver_id=delivery_driver.id if driver else None,
            recipient_name=recipient, recipient_phone="00000000",
            origin="Origin", destination="Destination", weight_kg=2.5,
            status=status,
        )
        if created_at is not None:
            row.created_at = created_at
        db.session.add(row)
        db.session.flush()
        for _ in range(failed_events):
            db.session.add(ShipmentEvent(shipment_id=row.id, changed_by_id=delivery_driver.id,
                                         status=DELIVERY_FAILED, note="Delivery failed"))
        db.session.commit()
        return row.id, row.tracking_number


def csv_rows(response):
    assert response.headers["Content-Type"].startswith("text/csv")
    assert response.data.startswith(b"\xef\xbb\xbf")
    decoded = response.data.decode("utf-8-sig")
    return list(csv.reader(StringIO(decoded)))


def test_empty_dashboard_and_report_show_no_division_by_zero(client):
    login(client)
    dashboard = client.get("/dashboard")
    report = client.get("/reports/")
    assert dashboard.status_code == 200 and report.status_code == 200
    assert b"Delivery Success Rate" in dashboard.data
    assert b"N/A" in dashboard.data
    assert b"No shipments match these filters" in report.data


def test_dashboard_preserves_old_recent_shipments(app, client):
    _, tracking = add_shipment(app)
    login(client)
    result = client.get("/dashboard")
    assert b"Recent Shipments" in result.data
    assert tracking.encode() in result.data
    assert b"Total Shipments" in result.data


def test_dashboard_summary_success_rate_excludes_cancelled_and_pending(app, client):
    for status in (DELIVERED, DELIVERED, RETURNED, CANCELLED, "pending"):
        add_shipment(app, status=status)
    login(client)
    result = client.get("/dashboard")
    assert b"66.7%" in result.data
    with app.app_context():
        staff = db.session.scalar(db.select(User).where(User.role == "staff"))
        stats = dashboard_data(staff)["stats"]
        assert stats["total"] == 5
        assert stats["success_rate"] == 66.7
        assert stats["delivered"] == 2 and stats["returned"] == 1


def test_failed_attempts_count_events_even_after_recovery(app):
    add_shipment(app, status=DELIVERED, driver=True, failed_events=2)
    add_shipment(app, status=DELIVERY_FAILED, driver=True, failed_events=1)
    with app.app_context():
        staff = db.session.scalar(db.select(User).where(User.role == "staff"))
        stats = dashboard_data(staff)["stats"]
        assert stats["failed_attempts"] == 3
        assert stats["failed"] == 1


def test_dashboard_attentions_only_currently_failed(app, client):
    _, failed_tracking = add_shipment(app, status=DELIVERY_FAILED, driver=True)
    _, delivered_tracking = add_shipment(app, status=DELIVERED, driver=True)
    login(client)
    result = client.get("/dashboard").data.decode()
    section = result.split("Requires Attention", 1)[1].split("Driver Workload", 1)[0]
    assert failed_tracking in section
    assert delivered_tracking not in section


def test_driver_dashboard_is_scoped_to_own_assignments(app, client):
    _, own_tracking = add_shipment(app, status=ASSIGNED, driver=True)
    _, other_tracking = add_shipment(app, status=DELIVERED, driver=False)
    login(client, "driver")
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert own_tracking.encode() in response.data
    assert other_tracking.encode() not in response.data
    assert b"Only your assigned shipments" in response.data
    assert b"Driver Workload" not in response.data
    assert b"View Reports" not in response.data


def test_driver_workload_show_correct_active_and_delivered_counts(app):
    add_shipment(app, status=ASSIGNED, driver=True)
    add_shipment(app, status=DELIVERED, driver=True)
    add_shipment(app, status=RETURNED, driver=True)
    with app.app_context():
        from app.services.analytics import driver_workload
        workload = driver_workload()
        target = next(row for row in workload if row["name"] == "Driver User")
        assert target["active"] == 1 and target["delivered"] == 1


def test_daily_trend_has_fourteen_days_including_zeroes(app):
    today = datetime.now(timezone.utc).date()
    add_shipment(app, created_at=datetime.combine(today, datetime.min.time(), timezone.utc))
    add_shipment(app, created_at=datetime.combine(today - timedelta(days=20), datetime.min.time(), timezone.utc))
    with app.app_context():
        from app.services.analytics import daily_created
        points = daily_created(today=today)
        assert len(points) == 14
        assert sum(row["count"] for row in points) == 1
        assert points[-1]["count"] == 1


@pytest.mark.parametrize("role", ["admin", "staff"])
def test_report_access_for_authorized_roles(client, role):
    login(client, role)
    result = client.get("/reports/")
    assert result.status_code == 200
    assert b"Logistics Reports" in result.data
    assert b"Download CSV" in result.data


def test_driver_cannot_access_report_or_download(client):
    login(client, "driver")
    assert client.get("/reports/").status_code == 403
    assert client.get("/reports/export.csv").status_code == 403


def test_anonymous_report_redirects_to_login(client):
    assert client.get("/reports/").status_code == 302
    assert client.get("/reports/export.csv").status_code == 302


def test_report_status_filter_applies_to_page_summary_and_csv(app, client):
    _, d = add_shipment(app, status=DELIVERED)
    _, p = add_shipment(app, status="pending")
    login(client, "staff")
    page = client.get("/reports/?status=delivered")
    assert d.encode() in page.data and p.encode() not in page.data
    rows = csv_rows(client.get("/reports/export.csv?status=delivered"))
    assert len(rows) == 2 and rows[1][0] == d


def test_report_driver_filter_includes_only_selected_driver(app, client):
    _, yes_tracking = add_shipment(app, driver=True)
    _, no_tracking = add_shipment(app, driver=False)
    with app.app_context():
        driver_id = db.session.scalar(db.select(User.id).where(User.role == "driver"))
    login(client)
    page = client.get(f"/reports/?driver_id={driver_id}")
    assert yes_tracking.encode() in page.data
    assert no_tracking.encode() not in page.data
    rows = csv_rows(client.get(f"/reports/export.csv?driver_id={driver_id}"))
    assert len(rows) == 2 and rows[1][0] == yes_tracking


def test_date_filter_inclusive_to_date_uses_utc_days(app, client):
    day = datetime(2026, 10, 12, 23, 59, tzinfo=timezone.utc)
    _, inside = add_shipment(app, created_at=day)
    _, outside = add_shipment(app, created_at=day + timedelta(minutes=1))
    login(client)
    query = "from_date=2026-10-12&to_date=2026-10-12"
    page = client.get("/reports/?" + query)
    assert inside.encode() in page.data and outside.encode() not in page.data
    rows = csv_rows(client.get("/reports/export.csv?" + query))
    assert len(rows) == 2 and rows[1][0] == inside


def test_report_multiple_filters_are_intersection(app, client):
    add_shipment(app, status=DELIVERED, driver=True)
    add_shipment(app, status="pending", driver=True)
    add_shipment(app, status=DELIVERED, driver=False)
    with app.app_context():
        driver_id = db.session.scalar(db.select(User.id).where(User.role == "driver"))
        stats = report_summary({"status": "delivered", "driver_id": driver_id})
        assert stats["total"] == 1 and stats["delivered"] == 1
    login(client)
    rows = csv_rows(client.get(f"/reports/export.csv?status=delivered&driver_id={driver_id}"))
    assert len(rows) == 2


@pytest.mark.parametrize("query", [
    "from_date=2026-02-30", "to_date=abc", "from_date=2026-10-15&to_date=2026-10-01",
    "status=unsafe", "driver_id=-1", "driver_id=NaN", "driver_id=0",
    "to_date=9999-12-31", "driver_id=" + "9" * 5000,
])
def test_bad_filters_rejected_for_both_formats(client, query):
    login(client)
    assert client.get("/reports/?" + query).status_code == 400
    assert client.get("/reports/export.csv?" + query).status_code == 400


def test_csv_includes_bom_excel_headers_and_correct_download_headers(app, client):
    _, tracking = add_shipment(app, recipient="王小明", customer_name="香港貨運")
    login(client)
    r = client.get("/reports/export.csv")
    rows = csv_rows(r)
    assert "attachment;" in r.headers["Content-Disposition"]
    assert "no-store" in r.headers["Cache-Control"]
    assert "Tracking Number" in rows[0]
    assert rows[1][0] == tracking
    assert "王小明" in rows[1] and "香港貨運" in rows[1]


@pytest.mark.parametrize("dangerous", ["=1+2", "+SUM(1,2)", "-2+3", "@SUM(2)", "  =HYPERLINK(\"evil\")", "\t=1+2"])
def test_csv_formula_injection_is_neutralized(app, client, dangerous):
    add_shipment(app, recipient=dangerous)
    login(client)
    rows = csv_rows(client.get("/reports/export.csv"))
    assert rows[1][3].startswith("'")


def test_csv_export_contains_all_filtered_rows_not_just_first_page(app, client):
    for index in range(25):
        add_shipment(app, recipient=f"Report Recipient {index}")
    login(client)
    report = client.get("/reports/")
    assert b"25 matching records" in report.data
    assert b"Page 1 of 2" in report.data
    rows = csv_rows(client.get("/reports/export.csv"))
    assert len(rows) == 26


def test_report_empty_csv_has_header_only(client):
    login(client)
    rows = csv_rows(client.get("/reports/export.csv?status=delivered"))
    assert len(rows) == 1


def test_reports_are_read_only(app, client):
    add_shipment(app)
    with app.app_context():
        before = db.session.scalar(db.select(db.func.count(Shipment.id)))
    login(client)
    client.get("/dashboard")
    client.get("/reports/")
    client.get("/reports/export.csv")
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(Shipment.id))) == before
