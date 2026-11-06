from datetime import datetime, timedelta, timezone

import pytest

from app.extensions import db
from app.models import Customer, Shipment, User
from app.services.analytics import dashboard_data
from app.services.delivery_monitoring import delivery_metrics, is_overdue


def seed(app):
    today = datetime.now(timezone.utc).date()
    with app.app_context():
        staff = db.session.scalar(db.select(User).where(User.role == 'staff'))
        driver = db.session.scalar(db.select(User).where(User.role == 'driver'))
        customer = Customer(name='Monitoring', phone='123', address='Hub')
        db.session.add(customer)
        db.session.flush()
        rows = [
            ('LATE-MINE', 'assigned', today - timedelta(days=1), None, driver.id),
            ('LATE-OTHER', 'delivery_failed', today - timedelta(days=1), None, None),
            ('DUE-TODAY', 'pending', today, None, None),
            ('NO-DATE', 'pending', None, None, None),
            ('CANCELLED', 'cancelled', today - timedelta(days=1), None, None),
            ('RETURNED', 'returned', today - timedelta(days=1), None, None),
            ('ON-TIME', 'delivered', today, datetime.combine(today, datetime.max.time()), None),
            ('LATE-DONE', 'delivered', today - timedelta(days=1), datetime.now(timezone.utc), None),
            ('UNKNOWN-DONE', 'delivered', today, None, None),
        ]
        for tracking, status, expected, delivered, driver_id in rows:
            db.session.add(Shipment(
                tracking_number=tracking, status=status, expected_delivery_date=expected,
                delivered_at=delivered, driver_id=driver_id, customer_id=customer.id,
                created_by_id=staff.id, recipient_name='Receiver', recipient_phone='123',
                origin='Hub', destination='Home', weight_kg=1))
        db.session.commit()
    return today


def login(client, role='staff'):
    client.post('/login', data={'email': f'{role}@example.com', 'password': 'test-password-123'})


def test_overdue_boundaries_and_on_time_denominator(app):
    today = seed(app)
    with app.app_context():
        rows = db.session.scalars(db.select(Shipment)).all()
        assert {s.tracking_number for s in rows if is_overdue(s, today)} == {'LATE-MINE', 'LATE-OTHER'}
        stats = delivery_metrics(today=today)
        assert stats == {'overdue': 2, 'on_time': 1, 'measured_deliveries': 2, 'on_time_rate': 50.0}
        driver = db.session.scalar(db.select(User).where(User.role == 'driver'))
        assert dashboard_data(driver)['stats']['overdue'] == 1


def test_empty_metrics(app):
    with app.app_context():
        assert delivery_metrics()['on_time_rate'] is None


@pytest.mark.parametrize('role', ['admin', 'staff', 'driver'])
def test_pages_and_filtered_csv(app, client, role):
    seed(app)
    login(client, role)
    result = client.get('/shipments/?overdue=1')
    assert result.status_code == 200
    assert b'LATE-MINE' in result.data and b'DUE-TODAY' not in result.data
    assert b'Overdue only' in result.data
    assert (b'LATE-OTHER' in result.data) == (role != 'driver')
    assert b'Overdue Shipments' in client.get('/dashboard').data
    if role != 'driver':
        report = client.get('/reports/?overdue=1')
        assert report.status_code == 200 and b'LATE-MINE' in report.data
        csv = client.get('/reports/export.csv?overdue=1')
        assert b'LATE-MINE' in csv.data and b'DUE-TODAY' not in csv.data
        assert client.get('/reports/?overdue=bad').status_code == 400


def test_filter_survives_pagination(app, client):
    seed(app)
    with app.app_context():
        source = db.session.scalar(db.select(Shipment).where(Shipment.tracking_number == 'LATE-MINE'))
        for n in range(22):
            db.session.add(Shipment(
                tracking_number=f'PAGE-{n}', customer_id=source.customer_id,
                created_by_id=source.created_by_id, recipient_name='Receiver', recipient_phone='123',
                origin='Hub', destination='Home', weight_kg=1, status='pending',
                expected_delivery_date=source.expected_delivery_date))
        db.session.commit()
    login(client)
    for url in ('/shipments/?overdue=1', '/reports/?overdue=1'):
        response = client.get(url)
        assert b'page=2' in response.data and b'overdue=1' in response.data


def test_customer_cannot_read_internal_monitoring(app, client):
    seed(app)
    with app.app_context():
        customer = db.session.scalar(db.select(Customer))
        user = User(full_name='Customer', email='customer@example.com', role='customer', customer_id=customer.id)
        user.set_password('test-password-123')
        db.session.add(user)
        db.session.commit()
    login(client, 'customer')
    assert client.get('/shipments/?overdue=1').status_code == 403
    assert client.get('/reports/?overdue=1').status_code == 403
