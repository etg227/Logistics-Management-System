from datetime import date

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import or_

from app.extensions import db
from app.forms import ShipmentForm
from app.models import Customer, Shipment, User
from app.models.shipment import (
    DELIVERY_FAILED, DRIVER_NEXT_STATUS, FAILURE_REASONS, OUT_FOR_DELIVERY,
    PENDING, STATUS_LABELS,
)
from app.permissions import roles_required
from app.services.shipment_service import (
    WorkflowError, advance_delivery, assign_driver, cancel_shipment,
    create_shipment, mark_delivery_failed, resolve_failed_delivery,
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


def _clean_form_fields(form):
    def trimmed(field):
        return (field.data or "").strip() or None
    return dict(
        recipient_name=form.recipient_name.data.strip(),
        recipient_phone=form.recipient_phone.data.strip(),
        origin=form.origin.data.strip(),
        destination=form.destination.data.strip(),
        description=trimmed(form.description),
        weight_kg=form.weight_kg.data,
        package_type=form.package_type.data or "parcel",
        length_cm=form.length_cm.data,
        width_cm=form.width_cm.data,
        height_cm=form.height_cm.data,
        delivery_instructions=trimmed(form.delivery_instructions),
        expected_delivery_date=form.expected_delivery_date.data,
    )


def _shipment_or_404(shipment_id):
    shipment = db.get_or_404(Shipment, shipment_id)
    if current_user.role == "driver" and shipment.driver_id != current_user.id:
        abort(403)
    return shipment


def _date_filter(raw):
    try:
        return date.fromisoformat(raw) if raw else None
    except ValueError:
        return None


@shipments_bp.get("/")
@login_required
@roles_required("admin", "staff", "driver")
def index():
    q = request.args.get("q", "").strip()[:100]
    status = request.args.get("status", "").strip()
    from_date = request.args.get("from_date", "").strip()
    to_date = request.args.get("to_date", "").strip()
    driver_id = request.args.get("driver_id", type=int)
    sort = request.args.get("sort", "newest")

    stmt = db.select(Shipment)
    if current_user.role == "driver":
        stmt = stmt.where(Shipment.driver_id == current_user.id)
    elif driver_id is not None and driver_id > 0:
        stmt = stmt.where(Shipment.driver_id == driver_id)
    if status in STATUS_LABELS:
        stmt = stmt.where(Shipment.status == status)
    if q:
        value = f"%{q}%"
        stmt = stmt.where(or_(Shipment.tracking_number.ilike(value),
                              Shipment.recipient_name.ilike(value)))
    if _date_filter(from_date):
        stmt = stmt.where(db.func.date(Shipment.created_at) >= from_date)
    if _date_filter(to_date):
        stmt = stmt.where(db.func.date(Shipment.created_at) <= to_date)
    if sort == "oldest":
        stmt = stmt.order_by(Shipment.created_at.asc(), Shipment.id.asc())
    else:
        sort = "newest"
        stmt = stmt.order_by(Shipment.created_at.desc(), Shipment.id.desc())
    pagination = db.paginate(stmt, page=request.args.get("page", 1, type=int),
                             per_page=10, error_out=False)
    drivers = []
    if current_user.role in ("admin", "staff"):
        drivers = db.session.scalars(db.select(User).where(User.role == "driver")
                                     .order_by(User.full_name)).all()
    if current_user.role == "driver":
        return render_template("shipments/driver_index.html", pagination=pagination,
                               statuses=STATUS_LABELS, q=q, status=status)
    return render_template(
        "shipments/index.html", pagination=pagination, statuses=STATUS_LABELS,
        q=q, status=status, from_date=from_date, to_date=to_date,
        driver_id=driver_id, drivers=drivers, sort=sort,
    )


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
                **_clean_form_fields(form),
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
    if current_user.role == "driver":
        return render_template("shipments/driver_detail.html", shipment=shipment,
                               next_status=DRIVER_NEXT_STATUS.get(shipment.status))
    return render_template(
        "shipments/detail.html", shipment=shipment, drivers=drivers,
        next_status=DRIVER_NEXT_STATUS.get(shipment.status), statuses=STATUS_LABELS,
        failure_reasons=FAILURE_REASONS,
    )


@shipments_bp.get("/<int:shipment_id>/confirm-delivery")
@login_required
@roles_required("driver")
def confirm_delivery_page(shipment_id):
    shipment = _shipment_or_404(shipment_id)
    if shipment.status != OUT_FOR_DELIVERY:
        abort(404)
    return render_template("shipments/confirm_delivery.html", shipment=shipment)


@shipments_bp.get("/<int:shipment_id>/report-failure")
@login_required
@roles_required("driver")
def report_failure_page(shipment_id):
    shipment = _shipment_or_404(shipment_id)
    if shipment.status != OUT_FOR_DELIVERY:
        abort(404)
    return render_template("shipments/report_failure.html", shipment=shipment,
                           failure_reasons=FAILURE_REASONS)


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
            for key, value in _clean_form_fields(form).items():
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
    else:
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
        requested_status = request.form.get("status", "")
        advance_delivery(
            shipment, requested_status, current_user.id,
            location=request.form.get("location", ""),
            received_by=request.form.get("received_by", ""),
            delivery_note=request.form.get("delivery_note", ""),
        )
        status_messages = {
            "picked_up": "Pickup confirmed.",
            "in_transit": "Shipment marked in transit.",
            "out_for_delivery": "Delivery attempt started.",
            "delivered": "Delivery confirmed.",
        }
        flash(status_messages.get(requested_status, "Delivery updated."), "success")
    except WorkflowError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("shipments.detail", shipment_id=shipment.id))


@shipments_bp.post("/<int:shipment_id>/fail")
@login_required
@roles_required("driver")
def fail(shipment_id):
    shipment = _shipment_or_404(shipment_id)
    try:
        mark_delivery_failed(
            shipment, current_user.id,
            reason=request.form.get("reason", ""),
            note=request.form.get("note", ""),
            location=request.form.get("location", ""),
        )
        flash("Delivery failed. Staff must review this shipment.", "warning")
    except WorkflowError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("shipments.detail", shipment_id=shipment.id))


@shipments_bp.post("/<int:shipment_id>/resolve")
@login_required
@roles_required("admin", "staff")
def resolve(shipment_id):
    shipment = db.get_or_404(Shipment, shipment_id)
    driver_id = request.form.get("driver_id", type=int)
    driver = db.session.get(User, driver_id) if driver_id is not None else None
    try:
        resolve_failed_delivery(
            shipment, current_user.id, action=request.form.get("action", ""),
            driver=driver, note=request.form.get("note", ""),
        )
        flash("Failed delivery resolved.", "success")
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
