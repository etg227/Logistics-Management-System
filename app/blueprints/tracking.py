from flask import Blueprint, render_template, request
from app.extensions import db
from app.models import Shipment

tracking_bp = Blueprint("tracking", __name__)

LOCATION_COORDINATES = {
    "kwun tong": [22.3122, 114.2250],
    "central": [22.2819, 114.1582],
    "tsim sha tsui": [22.2988, 114.1722],
    "sha tin": [22.3771, 114.1974],
    "mong kok": [22.3193, 114.1694],
    "sham shui po": [22.3307, 114.1622],
    "causeway bay": [22.2805, 114.1847],
    "tsuen wan": [22.3707, 114.1140],
}
DEFAULT_COORDINATES = [22.3193, 114.1694]


def _region_coordinates(location):
    normalized = (location or "").casefold()
    for region, coordinates in LOCATION_COORDINATES.items():
        if region in normalized:
            return coordinates
    return DEFAULT_COORDINATES


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
                           shipment=shipment, not_found=not_found,
                           origin_coordinates=_region_coordinates(shipment.origin) if shipment else None,
                           destination_coordinates=_region_coordinates(shipment.destination) if shipment else None)
