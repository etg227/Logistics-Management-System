from datetime import datetime, timezone
from uuid import uuid4

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required

from app.extensions import db
from app.feature_forms import InvoiceForm
from app.models import Customer, Invoice, Shipment, User
from app.permissions import roles_required
from app.services.notifications import create_notification

invoices_bp = Blueprint("invoices", __name__, url_prefix="/invoices")


def _populate(form):
    customers = db.session.scalars(db.select(Customer).order_by(Customer.name)).all()
    form.customer_id.choices = [(c.id, f"{c.name} (#{c.id})") for c in customers]
    shipments = db.session.scalars(db.select(Shipment).order_by(Shipment.created_at.desc())).all()
    form.shipment_id.choices = [(0, "No shipment linked")] + [
        (s.id, f"{s.tracking_number} - {s.recipient_name}") for s in shipments
    ]


@invoices_bp.get("/")
@login_required
@roles_required("admin", "staff")
def index():
    pagination = db.paginate(
        db.select(Invoice).order_by(Invoice.issued_at.desc(), Invoice.id.desc()),
        page=request.args.get("page", 1, type=int), per_page=10, error_out=False,
    )
    return render_template("invoices/index.html", pagination=pagination)


@invoices_bp.route("/new", methods=["GET", "POST"])
@login_required
@roles_required("admin", "staff")
def create():
    form = InvoiceForm()
    _populate(form)
    if form.validate_on_submit():
        shipment_id = form.shipment_id.data or None
        shipment = db.session.get(Shipment, shipment_id) if shipment_id else None
        if shipment and shipment.customer_id != form.customer_id.data:
            form.shipment_id.errors.append("Shipment does not belong to this customer.")
        elif shipment and db.session.scalar(db.select(Invoice.id).where(Invoice.shipment_id == shipment.id)):
            form.shipment_id.errors.append("This shipment already has an invoice.")
        else:
            invoice = Invoice(
                invoice_number=f"INV-{datetime.now(timezone.utc):%Y%m%d}-{uuid4().hex[:8].upper()}",
                customer_id=form.customer_id.data, shipment_id=shipment_id,
                subtotal=form.subtotal.data, surcharge=form.surcharge.data or 0,
                tax=form.tax.data or 0, due_date=form.due_date.data,
                notes=(form.notes.data or "").strip() or None,
            )
            db.session.add(invoice)
            db.session.flush()
            customer_users = db.session.scalars(db.select(User).where(
                User.customer_id == invoice.customer_id,
                User.is_active.is_(True))).all()
            for user in customer_users:
                create_notification(user.id, "New invoice issued",
                                    f"Invoice {invoice.invoice_number} total is {invoice.currency} {invoice.total:.2f}.",
                                    category="billing")
            db.session.commit()
            flash("Invoice issued.", "success")
            return redirect(url_for("invoices.index"))
    return render_template("invoices/form.html", form=form, title="New Invoice")


@invoices_bp.post("/<int:invoice_id>/paid")
@login_required
@roles_required("admin", "staff")
def mark_paid(invoice_id):
    invoice = db.get_or_404(Invoice, invoice_id)
    updated = db.session.execute(
        db.update(Invoice).where(Invoice.id == invoice_id, Invoice.status != "paid")
        .values(status="paid", paid_at=datetime.now(timezone.utc))
    )
    if updated.rowcount == 0:
        flash("Invoice is already paid.", "info")
        return redirect(url_for("invoices.index"))
    customer_users = db.session.scalars(db.select(User).where(
        User.customer_id == invoice.customer_id, User.is_active.is_(True))).all()
    for user in customer_users:
        create_notification(user.id, "Invoice paid",
                            f"Invoice {invoice.invoice_number} has been marked as paid.",
                            category="billing")
    db.session.commit()
    flash("Invoice marked as paid.", "success")
    return redirect(url_for("invoices.index"))
