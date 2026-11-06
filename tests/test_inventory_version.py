import re

from app.extensions import db
from app.models import InventoryItem, InventoryMovement, Notification
from tests.test_inventory_history import stock


def version(client, wid):
    page = client.get(f"/warehouses/{wid}")
    return re.search(rb'name="expected_version" value="(\d+)"', page.data).group(1).decode()


def test_stale_balance_form_rejected_even_when_quantity_returns_to_original(app, client):
    wid, iid = stock(app, client)
    other = app.test_client()
    other.post('/login', data={'email':'admin@example.com', 'password':'test-password-123'})
    stale = version(other, wid)
    for quantity in (7, 10):
        response = client.post(f'/warehouses/inventory/{iid}/adjust', data={
            'operation':'adjustment', 'quantity':quantity, 'reason':'Fresh count',
            'expected_version':version(client, wid)})
        assert response.status_code == 302
    with app.app_context():
        before_notices = db.session.scalar(db.select(db.func.count(Notification.id)))
    response = other.post(f'/warehouses/inventory/{iid}/adjust', data={
        'operation':'adjustment', 'quantity':8, 'reason':'Stale count', 'expected_version':stale},
        follow_redirects=True)
    assert b'Stock changed' in response.data
    with app.app_context():
        assert db.session.get(InventoryItem, iid).quantity == 10
        assert db.session.get(InventoryItem, iid).version == 2
        assert db.session.scalar(db.select(db.func.count(InventoryMovement.id))) == 3
        assert db.session.scalar(db.select(db.func.count(Notification.id))) == before_notices


def test_balance_requires_version_but_receipts_use_current_balance(app, client):
    wid, iid = stock(app, client)
    for invalid in (None, 'bad', '-1'):
        data = {'quantity':2, 'reason':'Count'}
        if invalid is not None:
            data['expected_version'] = invalid
        client.post(f'/warehouses/inventory/{iid}/adjust', data=data)
    for _ in range(2):
        client.post(f'/warehouses/inventory/{iid}/adjust', data={
            'operation':'received', 'quantity':2, 'reason':'Receipt', 'expected_version':'0'})
    with app.app_context():
        item = db.session.get(InventoryItem, iid)
        assert item.quantity == 14 and item.version == 2
        assert db.session.scalar(db.select(db.func.count(InventoryMovement.id))) == 3


def test_version_migration_preserves_existing_ledger(tmp_path):
    from datetime import datetime, timezone
    from flask_migrate import upgrade, downgrade
    from sqlalchemy import MetaData, Table, select
    from app import create_app
    from app.models import Warehouse

    app = create_app({'TESTING':True, 'SECRET_KEY':'migration-only',
                      'SQLALCHEMY_DATABASE_URI':'sqlite:///' + (tmp_path / 'version.db').as_posix()})
    with app.app_context():
        upgrade(revision='f13b7c9d204a')
        warehouse = Warehouse(name='Old hub', location='Hub', capacity=10)
        db.session.add(warehouse)
        db.session.flush()
        old_items = Table('inventory_items', MetaData(), autoload_with=db.engine)
        iid = db.session.execute(old_items.insert().values(
            warehouse_id=warehouse.id, sku='OLD', name='Old stock', quantity=17,
            updated_at=datetime.now(timezone.utc))).inserted_primary_key[0]
        movement = InventoryMovement(item_id=iid, movement_type='opening',
                                     quantity_before=0, quantity_change=17, quantity_after=17,
                                     reason='Existing ledger')
        db.session.add(movement)
        db.session.commit()
        mid = movement.id
        db.session.remove()
        upgrade()
        item = db.session.get(InventoryItem, iid)
        assert item.quantity == 17 and item.version == 0
        assert db.session.get(InventoryMovement, mid).reason == 'Existing ledger'
        assert db.session.scalar(db.select(db.func.count(InventoryMovement.id))) == 1
        db.session.remove()
        downgrade(revision='f13b7c9d204a')
        assert db.session.scalar(select(old_items.c.quantity).where(old_items.c.id == iid)) == 17
        assert db.session.get(InventoryMovement, mid).reason == 'Existing ledger'
        db.session.remove()
        upgrade()
        assert db.session.get(InventoryItem, iid).version == 0
        assert db.session.scalar(db.select(db.func.count(InventoryMovement.id))) == 1
        db.session.remove()
        db.engine.dispose()
