from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import login_required
from sqlalchemy import or_

from app.extensions import db
from app.forms import CustomerForm
from app.models import Customer
from app.permissions import roles_required

customers_bp = Blueprint("customers", __name__, url_prefix="/customers")


@customers_bp.get("/")
@login_required
@roles_required("admin", "staff")
def index():
    search = request.args.get("q", "").strip()[:100]
    stmt = db.select(Customer)
    if search:
        value = f"%{search}%"
        stmt = stmt.where(or_(Customer.name.ilike(value), Customer.phone.ilike(value),
                              Customer.email.ilike(value)))
    stmt = stmt.order_by(Customer.id.desc())
    pagination = db.paginate(stmt, page=request.args.get("page", 1, type=int),
                             per_page=10, error_out=False)
    return render_template("customers/index.html", pagination=pagination, q=search)


@customers_bp.route("/new", methods=["GET", "POST"])
@login_required
@roles_required("admin", "staff")
def create():
    form = CustomerForm()
    if form.validate_on_submit():
        customer = Customer(
            name=form.name.data.strip(),
            email=(form.email.data or "").strip().lower() or None,
            phone=form.phone.data.strip(),
            address=form.address.data.strip(),
        )
        db.session.add(customer)
        db.session.commit()
        flash("Customer created successfully.", "success")
        return redirect(url_for("customers.index"))
    return render_template("customers/form.html", form=form, title="New Customer")


@customers_bp.route("/<int:customer_id>/edit", methods=["GET", "POST"])
@login_required
@roles_required("admin", "staff")
def edit(customer_id):
    customer = db.get_or_404(Customer, customer_id)
    form = CustomerForm(obj=customer)
    if form.validate_on_submit():
        customer.name = form.name.data.strip()
        customer.email = (form.email.data or "").strip().lower() or None
        customer.phone = form.phone.data.strip()
        customer.address = form.address.data.strip()
        db.session.commit()
        flash("Customer updated successfully.", "success")
        return redirect(url_for("customers.index"))
    return render_template("customers/form.html", form=form, title="Edit Customer")


@customers_bp.post("/<int:customer_id>/toggle")
@login_required
@roles_required("admin", "staff")
def toggle(customer_id):
    customer = db.get_or_404(Customer, customer_id)
    customer.active = not customer.active
    db.session.commit()
    flash("Customer status updated.", "success")
    return redirect(url_for("customers.index"))