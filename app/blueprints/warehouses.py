from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required

from app.extensions import db
from app.feature_forms import InventoryItemForm, WarehouseForm
from app.models import InventoryItem, User, Warehouse
from app.permissions import roles_required
from app.services.notifications import create_notification

warehouses_bp = Blueprint("warehouses", __name__, url_prefix="/warehouses")


@warehouses_bp.get("/")
@login_required
@roles_required("admin", "staff")
def index():
    warehouses = db.session.scalars(db.select(Warehouse).order_by(Warehouse.name)).all()
    return render_template("warehouses/index.html", warehouses=warehouses)


@warehouses_bp.route("/new", methods=["GET", "POST"])
@login_required
@roles_required("admin", "staff")
def create():
    form = WarehouseForm()
    if form.validate_on_submit():
        warehouse = Warehouse(name=form.name.data.strip(), location=form.location.data.strip(),
                              capacity=form.capacity.data)
        db.session.add(warehouse)
        db.session.commit()
        flash("Warehouse created.", "success")
        return redirect(url_for("warehouses.detail", warehouse_id=warehouse.id))
    return render_template("warehouses/form.html", form=form, title="New Warehouse")


@warehouses_bp.get("/<int:warehouse_id>")
@login_required
@roles_required("admin", "staff")
def detail(warehouse_id):
    warehouse = db.get_or_404(Warehouse, warehouse_id)
    form = InventoryItemForm()
    return render_template("warehouses/detail.html", warehouse=warehouse, form=form)


@warehouses_bp.post("/<int:warehouse_id>/inventory/new")
@login_required
@roles_required("admin", "staff")
def add_inventory(warehouse_id):
    warehouse = db.get_or_404(Warehouse, warehouse_id)
    form = InventoryItemForm()
    if form.validate_on_submit():
        item = InventoryItem(warehouse_id=warehouse.id, sku=form.sku.data.strip().upper(),
                             name=form.name.data.strip(), quantity=form.quantity.data,
                             reorder_level=form.reorder_level.data,
                             unit=form.unit.data.strip())
        db.session.add(item)
        db.session.commit()
        flash("Inventory item added.", "success")
    return redirect(url_for("warehouses.detail", warehouse_id=warehouse.id))


@warehouses_bp.post("/inventory/<int:item_id>/adjust")
@login_required
@roles_required("admin", "staff")
def adjust_inventory(item_id):
    item = db.get_or_404(InventoryItem, item_id)
    try:
        quantity = int((request.form.get("quantity") or "").strip())
        if quantity < 0:
            raise ValueError
    except ValueError:
        flash("Quantity must be a non-negative whole number.", "danger")
    else:
        item.quantity = quantity
        if item.quantity <= item.reorder_level:
            operations_users = db.session.scalars(db.select(User).where(
                User.role.in_(["admin", "staff"]), User.is_active.is_(True))).all()
            for user in operations_users:
                create_notification(
                    user.id, "Low inventory alert",
                    f"{item.name} ({item.sku}) at {item.warehouse.name} is at {item.quantity} {item.unit}.",
                    category="inventory",
                )
        db.session.commit()
        flash("Inventory quantity updated.", "success")
    return redirect(url_for("warehouses.detail", warehouse_id=item.warehouse_id))
