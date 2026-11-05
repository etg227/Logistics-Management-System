import pytest
from sqlalchemy import update

from app.extensions import db
from app.models import Customer, InventoryItem, InventoryMovement, Notification, User, Warehouse
from app.services.inventory_service import InventoryError, change_stock


def login(client, role='staff'):
    client.post('/login', data={'email': f'{role}@example.com', 'password': 'test-password-123'})


def stock(app, client):
    login(client)
    client.post('/warehouses/new', data={'name': 'Ledger Hub', 'location': 'Kowloon', 'capacity': 100})
    with app.app_context():
        wid = db.session.scalar(db.select(Warehouse.id))
    client.post(f'/warehouses/{wid}/inventory/new', data={
        'sku': 'BOX', 'name': 'Boxes', 'quantity': 10, 'reorder_level': 3, 'unit': 'units'})
    with app.app_context():
        return wid, db.session.scalar(db.select(InventoryItem.id))


def test_opening_receive_dispatch_adjust_and_history(app, client):
    wid, iid = stock(app, client)
    for operation, quantity, reason in [('received', 5, 'Supplier delivery'),
                                        ('dispatched', 12, 'Order shipped'),
                                        ('adjustment', 2, 'Stocktake correction')]:
        response = client.post(f'/warehouses/inventory/{iid}/adjust', data={
            'operation': operation, 'quantity': quantity, 'reason': reason}, follow_redirects=True)
        assert response.status_code == 200 and reason.encode() in response.data
    with app.app_context():
        moves = db.session.scalars(db.select(InventoryMovement).order_by(InventoryMovement.id)).all()
        assert [(m.quantity_before, m.quantity_change, m.quantity_after) for m in moves] == [
            (0, 10, 10), (10, 5, 15), (15, -12, 3), (3, -1, 2)]
        assert all(m.actor.role == 'staff' for m in moves)
        assert db.session.get(InventoryItem, iid).quantity == 2
        assert db.session.scalar(db.select(Notification.id).where(Notification.category == 'inventory'))
    assert b'Inventory Movement History' in client.get(f'/warehouses/{wid}').data


@pytest.mark.parametrize('operation,quantity,reason', [
    ('dispatched', 11, 'Too many'), ('received', 0, 'Zero'),
    ('adjustment', -1, 'Negative'), ('adjustment', 10, 'Unchanged'),
    ('received', 'abc', 'Invalid'), ('other', 1, 'Unknown'),
    ('received', 1, ''), ('received', 1, 'x' * 256),
    ('adjustment', 100000001, 'Overflow'), ('dispatched', '1.5', 'Fraction'),
])
def test_invalid_movements_leave_stock_and_ledger_unchanged(app, client, operation, quantity, reason):
    _, iid = stock(app, client)
    client.post(f'/warehouses/inventory/{iid}/adjust', data={
        'operation': operation, 'quantity': quantity, 'reason': reason})
    with app.app_context():
        assert db.session.get(InventoryItem, iid).quantity == 10
        assert db.session.scalar(db.select(db.func.count(InventoryMovement.id))) == 1


@pytest.mark.parametrize('role', ['driver', 'customer'])
def test_history_and_movements_blocked_for_other_roles(app, client, role):
    wid, iid = stock(app, client)
    if role == 'customer':
        with app.app_context():
            customer = Customer(name='Customer', phone='123', address='Home')
            db.session.add(customer)
            db.session.flush()
            user = User(full_name='Customer', email='customer@example.com', role='customer', customer_id=customer.id)
            user.set_password('test-password-123')
            db.session.add(user)
            db.session.commit()
    client.post('/logout')
    login(client, role)
    assert client.get(f'/warehouses/{wid}').status_code == 403
    assert client.post(f'/warehouses/inventory/{iid}/adjust', data={
        'quantity': 0, 'reason': 'Forbidden'}).status_code == 403


def test_history_is_warehouse_scoped_and_paginated(app, client):
    wid, iid = stock(app, client)
    with app.app_context():
        other = Warehouse(name='Other', location='Other', capacity=10)
        db.session.add(other)
        db.session.flush()
        item = InventoryItem(warehouse_id=other.id, sku='SECRET', name='Private stock', quantity=1, reorder_level=0)
        db.session.add(item)
        db.session.flush()
        db.session.add(InventoryMovement(item_id=item.id, movement_type='opening', quantity_before=0,
                                         quantity_change=1, quantity_after=1, reason='OTHER WAREHOUSE'))
        db.session.commit()
    for n in range(21):
        client.post(f'/warehouses/inventory/{iid}/adjust', data={
            'operation': 'received', 'quantity': 1, 'reason': f'Receipt {n:02}'})
    first = client.get(f'/warehouses/{wid}')
    second = client.get(f'/warehouses/{wid}?history_page=2')
    assert b'Receipt 20' in first.data and b'Receipt 00' not in first.data
    assert b'Receipt 00' in second.data and b'OTHER WAREHOUSE' not in first.data + second.data


def test_concurrent_stock_change_rejected(app, client):
    _, iid = stock(app, client)
    with app.app_context():
        item = db.session.get(InventoryItem, iid)
        actor = db.session.scalar(db.select(User).where(User.role == 'staff'))
        db.session.execute(update(InventoryItem).where(InventoryItem.id == iid).values(quantity=7),
                           execution_options={'synchronize_session': False})
        with pytest.raises(InventoryError, match='Stock changed'):
            change_stock(item, actor_id=actor.id, operation='dispatched', quantity=2, reason='Stale request')
        db.session.rollback()


def test_transaction_rollback_restores_stock_and_history(app, client):
    _, iid = stock(app, client)
    with app.app_context():
        actor = db.session.scalar(db.select(User).where(User.role == 'staff'))
        change_stock(db.session.get(InventoryItem, iid), actor_id=actor.id,
                     operation='received', quantity=4, reason='Rolled back')
        db.session.flush()
        db.session.rollback()
        assert db.session.get(InventoryItem, iid).quantity == 10
        assert db.session.scalar(db.select(db.func.count(InventoryMovement.id))) == 1


def test_migration_preserves_existing_stock_and_backfills_opening(tmp_path):
    from flask_migrate import downgrade, upgrade
    from sqlalchemy import inspect
    from app import create_app

    application = create_app({
        'TESTING': True, 'SECRET_KEY': 'migration-test',
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///' + (tmp_path / 'migration.db').as_posix(),
    })
    with application.app_context():
        upgrade(revision='e82a92c7706c')
        warehouse = Warehouse(name='Existing Hub', location='Hub', capacity=100)
        db.session.add(warehouse)
        db.session.flush()
        item = InventoryItem(warehouse_id=warehouse.id, sku='EXISTING', name='Existing stock',
                             quantity=17, reorder_level=2)
        db.session.add(item)
        db.session.commit()
        iid = item.id
        db.session.remove()
        upgrade()
        movement = db.session.scalar(db.select(InventoryMovement))
        assert movement.quantity_after == 17 and movement.quantity_change == 17
        assert movement.actor_id is None and 'earlier movements were not recorded' in movement.reason
        assert db.session.get(InventoryItem, iid).quantity == 17
        db.session.remove()
        downgrade(revision='e82a92c7706c')
        assert 'inventory_movements' not in inspect(db.engine).get_table_names()
        assert db.session.get(InventoryItem, iid).quantity == 17
        db.session.remove()
        upgrade()
        assert db.session.scalar(db.select(db.func.count(InventoryMovement.id))) == 1
        db.session.remove()
        db.engine.dispose()
