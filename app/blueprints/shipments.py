from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_

from app.extensions import db
from app.forms import ShipmentForm
from app.models import Customer, Shipment, User
from app.models.shipment import PENDING, STATUS_LABELS, DRIVER_NEXT_STATUS
from app.permissions import roles_required
from app.services.shipment_service import (
    WorkflowError, advance_delivery, assign_driver, cancel_shipment, create_shipment,
)

shipments_bp = Blueprint("shipments", __name__, url_prefix="/shipments")


def _select_customers(form, extra_customer_id=None):
    customers = db.session.scalars(
        db.select(Customer).where(Customer.active.is_(True)).order_by(Customer.name)
    ).all()
    if extra_customer_id and all(c.id != extra_customer_id for c in customers):
        old = db.session.get(Customer, extra_customer_id)
        if old is not None:
            customers.append(old)
    form.customer_id.choices = [(c.id, f"{c.name} (#{c.id})") for c in customers]


def _form_fields(form):
    return dict(
        recipient_name=form.recipient_name.data.strip(),
        recipient_phone=form.recipient_phone.data.strip(),
        origin=form.origin.data.strip(),
        destination=form.destination.data.strip(),
        description=(form.description.data or "").strip() or None,
        weight_kg=form.weight_kg.data,
    )


def _shipment_or_404(shipment_id):
    shipment = db.get_or_404(Shipment, shipment_id)
    if current_user.role == "driver" and shipment.driver_id != current_user.id:
        abort(403)
    return shipment


@shipments_bp.get("/")
@login_required
@roles_required("admin", "staff", "driver")
def index():
    search = request.args.get("q", "").strip()[:100]
    status = request.args.get("status", "").strip()
    stmt = db.select(Shipment)
    if current_user.role == "driver":
        stmt = stmt.where(Shipment.driver_id == current_user.id)
    if status in STATUS_LABELS:
        stmt = stmt.where(Shipment.status == status)
    if search:
        value = f"%{search}%"
        stmt = stmt.where(or_(Shipment.tracking_number.ilike(value),
                              Shipment.recipient_name.ilike(value)))
    stmt = stmt.order_by(Shipment.created_at.desc(), Shipment.id.desc())
    pagination = db.paginate(stmt, page=request.args.get("page", 1, type=int),
                             per_page=10, error_out=False)
    return render_template("shipments/index.html", pagination=pagination,
                           statuses=STATUS_LABELS, q=search, status=status)


@shipments_bp.route("/new", methods=["GET", "POST"])
@login_required
@roles_required("admin", "staff")
def create():
    form = ShipmentForm()
    _select_customers(form)
    if form.validate_on_submit():
        customer = db.session.get(Customer, form.customer_id.data)
        if customer is None or not customer.active:
            form.customer_id.errors.append("Please select an active customer.")
        else:
            shipment = create_shipment(
                customer_id=customer.id, created_by_id=current_user.id,
                **_form_fields(form),
            )
            flash(f"Shipment {shipment.tracking_number} created.", "success")
            return redirect(url_for("shipments.detail", shipment_id=shipment.id))
    return render_template("shipments/form.html", form=form, title="Create Shipment")


@shipments_bp.get("/<int:shipment_id>")
@login_required
@roles_required("admin", "staff", "driver")
def detail(shipment_id):
    shipment = _shipment_or_404(shipment_id)
    drivers = []
    if current_user.role in ("admin", "staff"):
        drivers = db.session.scalars(
            db.select(User).where(User.role == "driver", User.is_active.is_(True))
            .order_by(User.full_name)
        ).all()
    next_status = DRIVER_NEXT_STATUS.get(shipment.status)
    return render_template("shipments/detail.html", shipment=shipment,
                           drivers=drivers, next_status=next_status,
                           statuses=STATUS_LABELS)


@shipments_bp.route("/<int:shipment_id>/edit", methods=["GET", "POST"])
@login_required
@roles_required("admin", "staff")
def edit(shipment_id):
    shipment = db.get_or_404(Shipment, shipment_id)
    if shipment.status != PENDING:
        flash("Only pending shipments can be edited.", "warning")
        return redirect(url_for("shipments.detail", shipment_id=shipment.id))
    form = ShipmentForm(obj=shipment)
    _select_customers(form, shipment.customer_id)
    if form.validate_on_submit():
        customer = db.session.get(Customer, form.customer_id.data)
        if customer is None or not customer.active:
            form.customer_id.errors.append("Please select an active customer.")
        else:
            shipment.customer_id = customer.id
            for key, value in _form_fields(form).items():
                setattr(shipment, key, value)
            db.session.commit()
            flash("Shipment details updated.", "success")
            return redirect(url_for("shipments.detail", shipment_id=shipment.id))
    return render_template("shipments/form.html", form=form, title="Edit Shipment")


@shipments_bp.post("/<int:shipment_id>/assign")
@login_required
@roles_required("admin", "staff")
def assign(shipment_id):
    shipment = db.get_or_404(Shipment, shipment_id)
    driver_id = request.form.get("driver_id", type=int)
    driver = db.session.get(User, driver_id) if driver_id is not None else None
    if driver is None:
        flash("Select a valid driver.", "danger")
        return redirect(url_for("shipments.detail", shipment_id=shipment.id))
    try:
        assign_driver(shipment, driver, current_user.id)
        flash("Driver assigned successfully.", "success")
    except WorkflowError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("shipments.detail", shipment_id=shipment.id))


@shipments_bp.post("/<int:shipment_id>/advance")
@login_required
@roles_required("driver")
def advance(shipment_id):
    shipment = _shipment_or_404(shipment_id)
    try:
        advance_delivery(shipment, request.form.get("status", ""), current_user.id)
        flash("Delivery status updated.", "success")
    except WorkflowError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("shipments.detail", shipment_id=shipment.id))


@shipments_bp.post("/<int:shipment_id>/cancel")
@login_required
@roles_required("admin", "staff")
def cancel(shipment_id):
    shipment = db.get_or_404(Shipment, shipment_id)
    try:
        cancel_shipment(shipment, current_user.id)
        flash("Shipment cancelled.", "success")
    except WorkflowError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("shipments.detail", shipment_id=shipment.id))