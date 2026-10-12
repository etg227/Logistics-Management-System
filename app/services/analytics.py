"""Shared read-only operational analytics for Dashboard and Reports.

Dates are interpreted as UTC calendar days; reports select by shipment CREATED date.
A completion rate has a denominator of terminal delivery outcomes only:
Delivered / (Delivered + Returned). Cancelled and ongoing shipments are excluded.
"""
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import func

from app.extensions import db
from app.models import Shipment, ShipmentEvent, User
from app.models.shipment import (
    ASSIGNED, CANCELLED, DELIVERED, DELIVERY_FAILED, IN_TRANSIT,
    OUT_FOR_DELIVERY, PENDING, PICKED_UP, RETURNED, STATUS_LABELS,
)

ACTIVE_STATUSES = (ASSIGNED, PICKED_UP, IN_TRANSIT, OUT_FOR_DELIVERY)
TRANSIT_STATUSES = (PICKED_UP, IN_TRANSIT, OUT_FOR_DELIVERY)


def utc_day_range(from_date=None, to_date=None):
    """Return [inclusive UTC start, exclusive UTC end] of date-only filters."""
    start = datetime.combine(from_date, time.min, timezone.utc) if from_date else None
    end = (datetime.combine(to_date, time.min, timezone.utc) + timedelta(days=1)
           if to_date else None)
    return start, end


def shipment_conditions(*, from_date=None, to_date=None, status=None,
                        driver_id=None):
    conditions = []
    start, end = utc_day_range(from_date, to_date)
    if start is not None:
        conditions.append(Shipment.created_at >= start)
    if end is not None:
        conditions.append(Shipment.created_at < end)
    if status:
        conditions.append(Shipment.status == status)
    if driver_id is not None:
        conditions.append(Shipment.driver_id == driver_id)
    return conditions


def status_totals(conditions=()):
    result = dict(db.session.execute(
        db.select(Shipment.status, func.count(Shipment.id))
        .where(*conditions).group_by(Shipment.status)
    ).all())
    return {name: result.get(name, 0) for name in STATUS_LABELS}


def count_failure_events(conditions=(), *, actor_id=None):
    filters = [ShipmentEvent.status == DELIVERY_FAILED, *conditions]
    if actor_id is not None:
        filters.append(ShipmentEvent.changed_by_id == actor_id)
    return db.session.scalar(
        db.select(func.count(ShipmentEvent.id))
        .join(Shipment, Shipment.id == ShipmentEvent.shipment_id)
        .where(*filters)
    ) or 0


def summary_from_conditions(conditions=(), *, actor_id=None):
    counts = status_totals(conditions)
    delivered = counts[DELIVERED]
    returned = counts[RETURNED]
    completed = delivered + returned
    return {
        "total": sum(counts.values()),
        "pending": counts[PENDING] + counts[ASSIGNED],
        "in_transit": sum(counts[s] for s in TRANSIT_STATUSES),
        "active": sum(counts[s] for s in ACTIVE_STATUSES),
        "delivered": delivered,
        "failed": counts[DELIVERY_FAILED],
        "returned": returned,
        "cancelled": counts[CANCELLED],
        "failed_attempts": count_failure_events(conditions, actor_id=actor_id),
        "completed": completed,
        "success_rate": round(delivered * 100 / completed, 1) if completed else None,
        "counts": counts,
    }


def daily_created(conditions=(), *, days=14, today=None):
    """Fixed 14-day UTC series, including days with zero shipments."""
    today = today or datetime.now(timezone.utc).date()
    first = today - timedelta(days=days - 1)
    start, end = utc_day_range(first, today)
    results = dict(db.session.execute(
        db.select(func.date(Shipment.created_at), func.count(Shipment.id))
        .where(Shipment.created_at >= start, Shipment.created_at < end, *conditions)
        .group_by(func.date(Shipment.created_at))
    ).all())
    series = []
    for index in range(days):
        day = first + timedelta(days=index)
        series.append({"date": day.isoformat(), "label": day.strftime("%b %d"),
                       "count": results.get(day.isoformat(), 0)})
    max_count = max((row["count"] for row in series), default=0)
    for row in series:
        row["height"] = round(100 * row["count"] / max_count) if max_count else 0
    return series


def driver_workload():
    """Show active and completed shipments for current driver accounts."""
    drivers = db.session.scalars(db.select(User).where(User.role == "driver")
                                 .order_by(User.full_name, User.id)).all()
    statuses = db.session.execute(
        db.select(Shipment.driver_id, Shipment.status, func.count(Shipment.id))
        .where(Shipment.driver_id.is_not(None))
        .group_by(Shipment.driver_id, Shipment.status)
    ).all()
    per_driver = {}
    for uid, status, count in statuses:
        per_driver.setdefault(uid, {})[status] = count
    rows = []
    for driver in drivers:
        row = per_driver.get(driver.id, {})
        rows.append({
            "id": driver.id, "name": driver.full_name, "enabled": driver.is_active,
            "active": sum(row.get(status, 0) for status in ACTIVE_STATUSES),
            "delivered": row.get(DELIVERED, 0),
            "failed": row.get(DELIVERY_FAILED, 0),
        })
    rows.sort(key=lambda item: (-item["active"], item["name"].lower(), item["id"]))
    return rows


def dashboard_data(user):
    is_driver = user.role == "driver"
    conditions = shipment_conditions(driver_id=user.id if is_driver else None)
    summary = summary_from_conditions(conditions,
                                      actor_id=user.id if is_driver else None)
    recent = db.session.scalars(
        db.select(Shipment).where(*conditions)
        .order_by(Shipment.created_at.desc(), Shipment.id.desc()).limit(6)
    ).all()
    attention = []
    workload = []
    if not is_driver:
        attention = db.session.scalars(
            db.select(Shipment).where(Shipment.status == DELIVERY_FAILED)
            .order_by(Shipment.updated_at.desc(), Shipment.id.desc()).limit(6)
        ).all()
        workload = driver_workload()
    rows = []
    max_total = max(summary["counts"].values(), default=0)
    for code, label in STATUS_LABELS.items():
        total = summary["counts"][code]
        rows.append({"code": code, "label": label, "count": total,
                     "width": round(100 * total / max_total) if max_total else 0})
    return {
        "stats": summary, "recent": recent, "attention": attention,
        "workload": workload, "distribution": rows,
        "daily": daily_created(conditions),
        "is_driver": is_driver,
    }


def report_summary(filters):
    return summary_from_conditions(shipment_conditions(**filters))
