"""Delivery dates and statistics use UTC calendar days, like existing reports."""
from datetime import datetime, timezone

from sqlalchemy import func

from app.extensions import db
from app.models import Shipment
from app.models.shipment import CANCELLED, DELIVERED, RETURNED

TERMINAL_STATUSES = (CANCELLED, DELIVERED, RETURNED)


def overdue_conditions(today=None):
    today = today or datetime.now(timezone.utc).date()
    return (Shipment.expected_delivery_date < today,
            Shipment.status.not_in(TERMINAL_STATUSES))


def is_overdue(shipment, today=None):
    today = today or datetime.now(timezone.utc).date()
    return bool(shipment.expected_delivery_date
                and shipment.expected_delivery_date < today
                and shipment.status not in TERMINAL_STATUSES)


def delivery_metrics(conditions=(), today=None):
    overdue = db.session.scalar(db.select(func.count(Shipment.id)).where(
        *conditions, *overdue_conditions(today))) or 0
    eligible = (Shipment.status == DELIVERED,
                Shipment.expected_delivery_date.is_not(None),
                Shipment.delivered_at.is_not(None))
    measured = db.session.scalar(db.select(func.count(Shipment.id)).where(
        *conditions, *eligible)) or 0
    on_time = db.session.scalar(db.select(func.count(Shipment.id)).where(
        *conditions, *eligible,
        func.date(Shipment.delivered_at) <= Shipment.expected_delivery_date)) or 0
    return {"overdue": overdue, "on_time": on_time, "measured_deliveries": measured,
            "on_time_rate": round(on_time * 100 / measured, 1) if measured else None}
