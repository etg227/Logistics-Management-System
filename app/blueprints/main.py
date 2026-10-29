from flask import Blueprint, redirect, render_template, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models import Shipment
from app.models.shipment import (
    ASSIGNED, DELIVERED, DELIVERY_FAILED, IN_TRANSIT, OUT_FOR_DELIVERY, PENDING,
    PICKED_UP, RETURNED,
)
from app.permissions import roles_required
from app.services.analytics import dashboard_data

main_bp = Blueprint("main", __name__)

DRIVER_OPEN_STATUSES = (ASSIGNED, PICKED_UP, IN_TRANSIT, OUT_FOR_DELIVERY)
DRIVER_CLOSED_STATUSES = (DELIVERED, RETURNED)


@main_bp.get("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))
    return redirect(url_for("auth.login"))


@main_bp.get("/dashboard")
@login_required
def dashboard():
    data = dashboard_data(current_user)
    data.update(driver_tasks=[], unassigned=[], unassigned_count=0)
    if current_user.role == "driver":
        data["driver_tasks"] = db.session.scalars(
            db.select(Shipment)
            .where(Shipment.driver_id == current_user.id,
                   Shipment.status.in_((ASSIGNED, PICKED_UP, IN_TRANSIT,
                                        OUT_FOR_DELIVERY, DELIVERY_FAILED)))
            .order_by(Shipment.updated_at.desc(), Shipment.id.desc()).limit(12)
        ).all()
    elif current_user.role == "staff":
        condition = (Shipment.status == PENDING) & Shipment.driver_id.is_(None)
        data["unassigned_count"] = db.session.scalar(
            db.select(db.func.count(Shipment.id)).where(condition)) or 0
        data["unassigned"] = db.session.scalars(
            db.select(Shipment).where(condition)
            .order_by(Shipment.created_at.asc(), Shipment.id.asc()).limit(6)
        ).all()
    return render_template("main/dashboard.html", **data)


@main_bp.get("/admin")
@login_required
@roles_required("admin")
def admin():
    return render_template("admin/overview.html")


@main_bp.get("/driver")
@login_required
@roles_required("driver")
def driver():
    """Driver worklist: what needs action now, what is in progress, what is closed."""
    mine = Shipment.driver_id == current_user.id

    open_tasks = db.session.scalars(
        db.select(Shipment)
        .where(mine, Shipment.status.in_(DRIVER_OPEN_STATUSES))
        .order_by(Shipment.updated_at.asc(), Shipment.id.asc())
    ).all()
    attention = db.session.scalars(
        db.select(Shipment)
        .where(mine, Shipment.status == DELIVERY_FAILED)
        .order_by(Shipment.updated_at.desc(), Shipment.id.desc())
        .limit(6)
    ).all()
    attention_total = db.session.scalar(
        db.select(db.func.count(Shipment.id))
        .where(mine, Shipment.status == DELIVERY_FAILED)
    ) or 0
    recent = db.session.scalars(
        db.select(Shipment)
        .where(mine, Shipment.status.in_(DRIVER_CLOSED_STATUSES))
        .order_by(Shipment.updated_at.desc(), Shipment.id.desc())
        .limit(5)
    ).all()
    delivered_total = db.session.scalar(
        db.select(db.func.count(Shipment.id))
        .where(mine, Shipment.status == DELIVERED)
    ) or 0

    return render_template(
        "main/driver_portal.html",
        action_now=[s for s in open_tasks if s.status == OUT_FOR_DELIVERY],
        in_progress=[s for s in open_tasks if s.status != OUT_FOR_DELIVERY],
        attention=attention,
        attention_total=attention_total,
        recent=recent,
        open_count=len(open_tasks),
        delivered_total=delivered_total,
    )
