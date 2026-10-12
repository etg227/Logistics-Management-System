"""CargoFlow role-specific UX and safe single-outcome delivery forms."""
from app.extensions import db
from app.models import Customer, Shipment, User
from app.services.shipment_service import assign_driver, create_shipment


def login(client, role):
    return client.post("/login", data={"email": f"{role}@example.com", "password": "test-password-123"}, follow_redirects=True)


def test_role_navigation_excludes_reports_for_driver(client):
    login(client, "driver")
    res = client.get("/dashboard")
    assert res.status_code == 200
    assert b"My Deliveries" in res.data
    assert b"Logistics Reports" not in res.data
    assert b"User Management" not in res.data
    assert b"Only your assigned shipments" in res.data


def test_staff_dashboard_has_queues_and_not_management_charts(client):
    login(client, "staff")
    res = client.get("/dashboard")
    assert res.status_code == 200
    assert b"Unassigned Shipments" in res.data
    assert b"Requires Attention" in res.data
    assert b"Driver Workload" not in res.data


def test_admin_dashboard_has_analytics(client):
    login(client, "admin")
    res = client.get("/dashboard")
    assert res.status_code == 200
    assert b"Status Distribution" in res.data
    assert b"Daily Shipment Trend" in res.data
    assert b"Driver Workload" in res.data


def seeded_task(app, status="out_for_delivery", assigned=True):
    with app.app_context():
        admin = db.session.scalar(db.select(User).where(User.role == "admin"))
        driver = db.session.scalar(db.select(User).where(User.role == "driver"))
        customer = Customer(name="UX Customer", phone="555-1111", address="Warehouse")
        db.session.add(customer)
        db.session.flush()
        s = create_shipment(customer_id=customer.id, created_by_id=admin.id,
                            recipient_name="Alex Chan", recipient_phone="555-2000",
                            origin="Kowloon", destination="Central", weight_kg=1.0)
        if assigned:
            assign_driver(s, driver, admin.id)
        s.status = status
        db.session.commit()
        return s.id


def test_driver_outcome_actions_are_distinct_and_have_no_shared_form(app, client):
    sid = seeded_task(app)
    login(client, "driver")
    page = client.get(f"/shipments/{sid}")
    assert page.status_code == 200
    assert b"Delivered successfully" in page.data
    assert b"Unable to deliver" in page.data
    assert b"name=\"received_by\"" not in page.data
    assert b"name=\"reason\"" not in page.data
    assert b"Update Delivery Status" not in page.data


def test_success_form_separate_from_failure_form(app, client):
    sid = seeded_task(app)
    login(client, "driver")
    page = client.get(f"/shipments/{sid}/confirm-delivery")
    assert page.status_code == 200
    assert b"name=\"received_by\"" in page.data
    assert b"name=\"reason\"" not in page.data
    failed = client.get(f"/shipments/{sid}/report-failure")
    assert failed.status_code == 200
    assert b"name=\"reason\"" in failed.data
    assert b"name=\"received_by\"" not in failed.data


def test_outcome_pages_reject_unassigned_driver(app, client):
    sid = seeded_task(app, assigned=False)
    login(client, "driver")
    assert client.get(f"/shipments/{sid}/confirm-delivery").status_code == 403
    assert client.get(f"/shipments/{sid}/report-failure").status_code == 403


def test_outcome_pages_only_at_out_for_delivery(app, client):
    sid = seeded_task(app, status="assigned")
    login(client, "driver")
    assert client.get(f"/shipments/{sid}/confirm-delivery").status_code == 404
    assert client.get(f"/shipments/{sid}/report-failure").status_code == 404
    page = client.get(f"/shipments/{sid}")
    assert b"Confirm Pickup" in page.data
    assert b"Update Delivery Status" not in page.data


def test_staff_cannot_open_driver_outcome_pages(app, client):
    sid = seeded_task(app)
    login(client, "staff")
    assert client.get(f"/shipments/{sid}/confirm-delivery").status_code == 403
    assert client.get(f"/shipments/{sid}/report-failure").status_code == 403


def test_driver_index_is_task_list_not_staff_table(app, client):
    sid = seeded_task(app)
    login(client, "driver")
    res = client.get("/shipments/")
    assert res.status_code == 200
    assert b"My Deliveries" in res.data
    assert b"View task" in res.data
    assert b"Alex Chan" in res.data


def test_staff_detail_preserves_redelivery_business_action(app, client):
    sid = seeded_task(app, status="delivery_failed")
    login(client, "staff")
    res = client.get(f"/shipments/{sid}")
    assert res.status_code == 200
    assert b"Schedule Redelivery" in res.data
    assert b"Return to Sender" in res.data
    assert b"Shipment Information" in res.data
    assert b"Status History" in res.data


def test_public_tracking_still_available(client):
    res = client.get("/tracking")
    assert res.status_code == 200
    assert b"Shipment Tracking" in res.data


def test_reports_export_unmodified_and_accessible(client):
    login(client, "staff")
    page = client.get("/reports/")
    assert page.status_code == 200
    assert b"Download CSV" in page.data
    assert client.get("/reports/export.csv").status_code == 200
