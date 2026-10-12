"""Shipment operations and delivery state transitions, independent of HTTP."""
from datetime import datetime, timezone
from uuid import uuid4

from app.extensions import db
from app.models import Shipment, ShipmentEvent
from app.models.shipment import (
    ASSIGNED, CANCELLED, DELIVERED, DELIVERY_FAILED, DRIVER_NEXT_STATUS,
    FAILURE_REASONS, OUT_FOR_DELIVERY, PENDING, RETURNED,
)


class WorkflowError(ValueError):
    """Requested operation violates shipment business rules."""


def _validate_optional_text(value, limit, name):
    value = (value or "").strip()
    if len(value) > limit:
        raise WorkflowError(f"{name} is too long (max {limit} characters).")
    return value


def _record_event(shipment, actor_id, status, note, location=""):
    note = _validate_optional_text(note, 255, "Event note")
    location = _validate_optional_text(location, 120, "Location")
    if location:
        shipment.current_location = location
    db.session.add(ShipmentEvent(
        shipment_id=shipment.id, changed_by_id=actor_id,
        status=status, note=note, location=location or None,
    ))


def create_shipment(*, customer_id, created_by_id, **fields):
    tracking_number = f"CF-{datetime.now(timezone.utc):%Y%m%d}-{uuid4().hex[:12].upper()}"
    shipment = Shipment(
        tracking_number=tracking_number, customer_id=customer_id,
        created_by_id=created_by_id, status=PENDING, **fields,
    )
    db.session.add(shipment)
    db.session.flush()
    _record_event(shipment, created_by_id, PENDING, "Shipment created")
    db.session.commit()
    return shipment


def assign_driver(shipment, driver, actor_id):
    if shipment.status not in (PENDING, ASSIGNED):
        raise WorkflowError("A driver can only be assigned before pickup.")
    if driver is None or driver.role != "driver" or not driver.is_active:
        raise WorkflowError("Please select an active driver account.")
    if shipment.driver_id == driver.id and shipment.status == ASSIGNED:
        raise WorkflowError("This driver is already assigned.")
    shipment.driver_id = driver.id
    shipment.status = ASSIGNED
    _record_event(shipment, actor_id, ASSIGNED, f"Assigned to {driver.full_name}"[:255])
    db.session.commit()


def advance_delivery(shipment, requested_status, actor_id, *,
                     location="", received_by="", delivery_note=""):
    if shipment.driver_id != actor_id:
        raise WorkflowError("This shipment is not assigned to you.")
    allowed = DRIVER_NEXT_STATUS.get(shipment.status)
    if not allowed or requested_status != allowed:
        raise WorkflowError("Invalid shipment status transition.")
    location = _validate_optional_text(location, 120, "Location")
    if requested_status == DELIVERED:
        signer = _validate_optional_text(received_by, 120, "Received by")
        note = _validate_optional_text(delivery_note, 300, "Delivery note")
        if not signer:
            raise WorkflowError("Please enter the recipient's name to confirm delivery.")
        shipment.received_by = signer
        shipment.delivery_note = note or None
        shipment.delivered_at = datetime.now(timezone.utc)
        event_note = f"Signed for by {signer}"[:255]
    else:
        event_note = "Delivery progress updated"
    if requested_status == OUT_FOR_DELIVERY:
        shipment.delivery_attempts = (shipment.delivery_attempts or 0) + 1
    shipment.status = requested_status
    _record_event(shipment, actor_id, requested_status, event_note, location)
    db.session.commit()


def mark_delivery_failed(shipment, actor_id, *, reason, note="", location=""):
    if shipment.driver_id != actor_id:
        raise WorkflowError("This shipment is not assigned to you.")
    if shipment.status != OUT_FOR_DELIVERY:
        raise WorkflowError("A delivery can only fail when it is out for delivery.")
    if reason not in FAILURE_REASONS:
        raise WorkflowError("Select a valid failure reason.")
    note = _validate_optional_text(note, 160, "Failure note")
    if reason == "other" and not note:
        raise WorkflowError("Explain the failure when selecting Other.")
    location = _validate_optional_text(location, 120, "Location")
    shipment.status = DELIVERY_FAILED
    shipment.last_failure_reason = reason
    if not shipment.delivery_attempts:
        shipment.delivery_attempts = 1  # existing pre-migration shipments
    message = "Delivery failed: " + FAILURE_REASONS[reason]
    if note:
        message += ". " + note
    _record_event(shipment, actor_id, DELIVERY_FAILED, message, location)
    db.session.commit()


def resolve_failed_delivery(shipment, actor_id, *, action, driver=None, note=""):
    if shipment.status != DELIVERY_FAILED:
        raise WorkflowError("Only failed deliveries can be resolved.")
    note = _validate_optional_text(note, 160, "Resolution note")
    if action == "redeliver":
        if driver is None or driver.role != "driver" or not driver.is_active:
            raise WorkflowError("Select an active driver for redelivery.")
        shipment.driver_id = driver.id
        shipment.status = ASSIGNED
        message = f"Redelivery assigned to {driver.full_name}"
    elif action == "return":
        shipment.status = RETURNED
        message = "Returned to sender"
    else:
        raise WorkflowError("Invalid delivery resolution.")
    if note:
        message += ". " + note
    _record_event(shipment, actor_id, shipment.status, message[:255])
    db.session.commit()


def cancel_shipment(shipment, actor_id):
    if shipment.status not in (PENDING, ASSIGNED):
        raise WorkflowError("Only shipments awaiting pickup can be cancelled.")
    shipment.status = CANCELLED
    _record_event(shipment, actor_id, CANCELLED, "Shipment cancelled")
    db.session.commit()
