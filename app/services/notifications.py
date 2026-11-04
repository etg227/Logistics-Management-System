from app.extensions import db
from app.models import Notification, User


def create_notification(user_id, title, message, *, category="info", shipment_id=None):
    notification = Notification(user_id=user_id, title=title, message=message,
                                category=category, shipment_id=shipment_id)
    db.session.add(notification)
    return notification


def notify_shipment_event(shipment, status_label, note=None, actor_id=None):
    """Create in-app notifications for the linked customer and assigned driver."""
    recipients = []
    if shipment.customer_id:
        recipients.extend(db.session.scalars(
            db.select(User).where(User.customer_id == shipment.customer_id,
                                  User.is_active.is_(True))
        ).all())
    if shipment.driver_id and shipment.driver_id != actor_id:
        driver = db.session.get(User, shipment.driver_id)
        if driver and driver.is_active:
            recipients.append(driver)
    if shipment.status == "delivery_failed":
        recipients.extend(db.session.scalars(
            db.select(User).where(User.role.in_(["admin", "staff"]),
                                  User.is_active.is_(True))
        ).all())
    title = f"Shipment {shipment.tracking_number} updated"
    message = f"Status: {status_label}."
    if note:
        message += f" {note}"
    for user in {user.id: user for user in recipients}.values():
        create_notification(user.id, title, message, category="shipment",
                            shipment_id=shipment.id)
