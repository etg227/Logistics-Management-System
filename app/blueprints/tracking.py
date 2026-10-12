from flask import Blueprint, render_template, request
from app.extensions import db
from app.models import Shipment

tracking_bp = Blueprint("tracking", __name__)


@tracking_bp.get("/tracking")
def index():
    tracking_number = request.args.get("q", "").strip().upper()[:40]
    shipment = None
    not_found = False
    if tracking_number:
        shipment = db.session.scalar(
            db.select(Shipment).where(Shipment.tracking_number == tracking_number)
        )
        not_found = shipment is None
    return render_template("tracking/index.html", tracking_number=tracking_number,
                           shipment=shipment, not_found=not_found)