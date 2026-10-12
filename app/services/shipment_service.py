from datetime import datetime, timezone
from uuid import uuid4

from app.extensions import db
from app.models import Shipment, ShipmentEvent
from app.models.shipment import (
    ASSIGNED, CANCELLED, DRIVER_NEXT_STATUS, PENDING,
)


class WorkflowError(ValueError):
    """Requested shipment operation violates its business rules."""


def create_shipment(*, customer_id, created_by_id, **fields):
    tracking_number = f"CF-{datetime.now(timezone.utc):%Y%m%d}-{uuid4().hex[:12].upper()}"
    shipment = Shipment(
        tracking_number=tracking_number,
        customer_id=customer_id,
        created_by_id=created_by_id,
        status=PENDING,
        **fields,
    )
    db.session.add(shipment)
    db.session.flush()
    db.session.add(ShipmentEvent(
        shipment_id=shipment.id, changed_by_id=created_by_id,
        status=PENDING, note="Shipment created",
    ))
    db.session.commit()
    return shipment


def assign_driver(shipment, driver, actor_id):
    if shipment.status not in (PENDING, ASSIGNED):
        raise WorkflowError("A driver can only be assigned before pickup.")
    if driver.role != "driver" or not driver.is_active:
        raise WorkflowError("Please select an active driver account.")
    if shipment.driver_id == driver.id and shipment.status == ASSIGNED:
        raise WorkflowError("This driver is already assigned.")
    shipment.driver_id = driver.id
    shipment.status = ASSIGNED
    db.session.add(ShipmentEvent(
        shipment_id=shipment.id, changed_by_id=actor_id,
        status=ASSIGNED, note=f"Assigned to {driver.full_name}",
    ))
    db.session.commit()


def advance_delivery(shipment, requested_status, actor_id):
    if shipment.driver_id != actor_id:
        raise WorkflowError("This shipment is not assigned to you.")
    allowed = DRIVER_NEXT_STATUS.get(shipment.status)
    if not allowed or requested_status != allowed:
        raise WorkflowError("Invalid shipment status transition.")
    shipment.status = requested_status
    db.session.add(ShipmentEvent(
        shipment_id=shipment.id, changed_by_id=actor_id,
        status=requested_status, note="Delivery progress updated",
    ))
    db.session.commit()


def cancel_shipment(shipment, actor_id):
    if shipment.status not in (PENDING, ASSIGNED):
        raise WorkflowError("Only shipments awaiting pickup can be cancelled.")
    shipment.status = CANCELLED
    db.session.add(ShipmentEvent(
        shipment_id=shipment.id, changed_by_id=actor_id,
        status=CANCELLED, note="Shipment cancelled",
    ))
    db.session.commit()