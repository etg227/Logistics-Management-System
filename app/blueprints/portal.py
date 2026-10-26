from flask import Blueprint, abort, render_template
from flask_login import current_user, login_required

from app.extensions import db
from app.models import Invoice, Notification, Shipment
from app.permissions import roles_required

portal_bp = Blueprint("portal", __name__, url_prefix="/portal")


@portal_bp.get("/")
@login_required
@roles_required("customer")
def index():
    if current_user.customer_id is None:
        abort(403)
    shipments = db.session.scalars(
        db.select(Shipment).where(Shipment.customer_id == current_user.customer_id)
        .order_by(Shipment.created_at.desc(), Shipment.id.desc())
    ).all()
    invoices = db.session.scalars(
        db.select(Invoice).where(Invoice.customer_id == current_user.customer_id)
        .order_by(Invoice.issued_at.desc(), Invoice.id.desc())
    ).all()
    notifications = db.session.scalars(
        db.select(Notification).where(Notification.user_id == current_user.id)
        .order_by(Notification.created_at.desc(), Notification.id.desc()).limit(5)
    ).all()
    return render_template("portal/index.html", shipments=shipments, invoices=invoices,
                           notifications=notifications)
