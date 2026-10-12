from flask import Blueprint, redirect, render_template, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models import Shipment
from app.models.shipment import (
    PENDING, ASSIGNED, PICKED_UP, IN_TRANSIT, OUT_FOR_DELIVERY, DELIVERED,
)
from app.permissions import roles_required

main_bp = Blueprint("main", __name__)


@main_bp.get("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    return redirect(url_for("auth.login"))


@main_bp.get("/dashboard")
@login_required
def dashboard():
    scope = []
    if current_user.role == "driver":
        scope.append(Shipment.driver_id == current_user.id)

    def count(*extra):
        stmt = db.select(db.func.count(Shipment.id)).where(*scope, *extra)
        return db.session.scalar(stmt) or 0

    stats = {
        "total": count(),
        "pending": count(Shipment.status.in_([PENDING, ASSIGNED])),
        "in_transit": count(Shipment.status.in_([PICKED_UP, IN_TRANSIT, OUT_FOR_DELIVERY])),
        "delivered": count(Shipment.status == DELIVERED),
    }
    recent = db.session.scalars(
        db.select(Shipment).where(*scope)
        .order_by(Shipment.created_at.desc(), Shipment.id.desc()).limit(5)
    ).all()
    return render_template("main/dashboard.html", stats=stats, recent=recent)


@main_bp.get("/admin")
@login_required
@roles_required("admin")
def admin():
    return render_template("main/role_page.html", title="Administration", role="Admin")


@main_bp.get("/driver")
@login_required
@roles_required("driver")
def driver():
    return render_template("main/role_page.html", title="Driver Portal", role="Driver")