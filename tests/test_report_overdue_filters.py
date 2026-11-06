import csv
import re
from html import unescape
from io import StringIO
from urllib.parse import parse_qs, urlencode, urlsplit

import pytest

from app.extensions import db
from app.models import User
from tests.test_overdue_monitoring import login, seed


def overdue_link(response):
    return unescape(re.search(
        rb'href="([^"]+)"[^>]*><span>Overdue Shipments</span>', response.data
    ).group(1).decode())


@pytest.mark.parametrize('role', ['admin', 'staff'])
def test_report_card_keeps_filters_and_csv_scope(app, client, role):
    today = seed(app)
    with app.app_context():
        driver_id = db.session.scalar(db.select(User.id).where(User.role == 'driver'))
    login(client, role)
    filters = {'from_date':today.isoformat(), 'to_date':today.isoformat(),
               'driver_id':str(driver_id), 'status':'assigned'}
    response = client.get('/reports/?' + urlencode({**filters, 'page':2}))
    assert response.status_code == 200
    target = overdue_link(response)
    parts = urlsplit(target)
    assert parts.path == '/reports/'
    assert parse_qs(parts.query) == {k:[v] for k,v in {**filters, 'overdue':'1'}.items()}
    result = client.get(target)
    assert result.status_code == 200
    assert b'LATE-MINE' in result.data and b'LATE-OTHER' not in result.data
    csv_link = unescape(re.search(rb'href="([^"]+)">Download CSV', result.data).group(1).decode())
    export = client.get(csv_link)
    rows = list(csv.reader(StringIO(export.data.decode('utf-8-sig'))))
    assert [row[0] for row in rows[1:]] == ['LATE-MINE']


def test_unfiltered_report_card_sets_overdue_without_empty_filter_values(app, client):
    seed(app)
    login(client)
    target = overdue_link(client.get('/reports/'))
    assert urlsplit(target).path == '/reports/'
    assert parse_qs(urlsplit(target).query, keep_blank_values=True) == {'overdue':['1']}
    response = client.get(target)
    assert response.status_code == 200
    assert b'LATE-MINE' in response.data and b'LATE-OTHER' in response.data
    assert b'DUE-TODAY' not in response.data
