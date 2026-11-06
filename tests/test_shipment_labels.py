import re
from html import unescape
from urllib.parse import parse_qs, urlsplit

import pytest

from app.extensions import db
from app.models import Shipment, User
from tests.test_logistics import assign, login, make_shipment


@pytest.mark.parametrize('role', ['admin', 'staff'])
def test_staff_detail_has_label_preview_and_local_qr_assets(app, client, role):
    sid = make_shipment(app)
    login(client, role)
    response = client.get(f'/shipments/{sid}')
    assert response.status_code == 200
    assert b'id="print-modal"' in response.data
    assert b'id="qrcode"' in response.data and b'id="qrcode-print"' in response.data
    assert b'Bob Receiver' in response.data and b'200 Destination Ave' in response.data
    assert response.data.count(b'vendor/qrcode.min.js') == 1
    assert response.data.count(b'js/shipment_label.js') == 1
    assert b'cdnjs.cloudflare.com' not in response.data
    assert client.get('/static/vendor/qrcode.min.js').status_code == 200


def test_tracking_link_is_encoded_and_label_stays_internal(app, client):
    sid = make_shipment(app)
    tracking = 'CF-QUOTE" & <tag>'
    with app.app_context():
        db.session.get(Shipment, sid).tracking_number = tracking
        db.session.commit()
    login(client, 'staff')
    response = client.get(f'/shipments/{sid}')
    href = unescape(re.search(rb'id="shipment-tracking-link"[^>]*href="([^"]+)"', response.data).group(1).decode())
    assert parse_qs(urlsplit(href).query)['q'] == [tracking]
    public = client.get(href)
    assert public.status_code == 200
    assert b'200 Destination Ave' not in public.data and b'Bob Receiver' not in public.data
    assert b'id="print-label-area"' not in public.data


def test_driver_and_anonymous_do_not_get_staff_label(app, client):
    sid = make_shipment(app)
    assert client.get(f'/shipments/{sid}').status_code == 302
    assign(app, sid)
    login(client, 'driver')
    response = client.get(f'/shipments/{sid}')
    assert response.status_code == 200
    assert b'id="print-modal"' not in response.data


def test_customer_cannot_open_internal_label_even_for_own_shipment(app, client):
    sid = make_shipment(app)
    with app.app_context():
        shipment = db.session.get(Shipment, sid)
        user = User(full_name='Customer', email='label-customer@example.com',
                    role='customer', customer_id=shipment.customer_id)
        user.set_password('test-password-123')
        db.session.add(user)
        db.session.commit()
    client.post('/login', data={'email':'label-customer@example.com','password':'test-password-123'})
    response = client.get(f'/shipments/{sid}')
    assert response.status_code == 403
    assert b'200 Destination Ave' not in response.data
