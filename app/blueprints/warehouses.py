from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.feature_forms import InventoryItemForm, WarehouseForm
from app.models import InventoryItem, InventoryMovement, Warehouse
from app.permissions import roles_required
from app.services.inventory_service import InventoryError, change_stock, record_opening_balance

warehouses_bp = Blueprint("warehouses", __name__, url_prefix="/warehouses")


def _render_detail(warehouse, form):
    movements = db.paginate(
        db.select(InventoryMovement).join(InventoryItem)
        .where(InventoryItem.warehouse_id == warehouse.id)
        .options(joinedload(InventoryMovement.item), joinedload(InventoryMovement.actor))
        .order_by(InventoryMovement.id.desc()),
        page=request.args.get("history_page", 1, type=int), per_page=20, error_out=False)
    return render_template("warehouses/detail.html", warehouse=warehouse, form=form,
                           movements=movements)


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
    return _render_detail(warehouse, form)


@warehouses_bp.post("/<int:warehouse_id>/inventory/new")
@login_required
@roles_required("admin", "staff")
def add_inventory(warehouse_id):
    warehouse = db.get_or_404(Warehouse, warehouse_id)
    form = InventoryItemForm()
    if form.validate_on_submit():
        sku = form.sku.data.strip().upper()
        duplicate = db.session.scalar(db.select(InventoryItem.id).where(
            InventoryItem.warehouse_id == warehouse.id, InventoryItem.sku == sku))
        if duplicate:
            form.sku.errors.append("This SKU already exists in this warehouse.")
        else:
            item = InventoryItem(warehouse_id=warehouse.id, sku=sku,
                                 name=form.name.data.strip(), quantity=form.quantity.data,
                                 reorder_level=form.reorder_level.data,
                                 unit=form.unit.data.strip())
            db.session.add(item)
            try:
                record_opening_balance(item, current_user.id)
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                form.sku.errors.append("This SKU already exists in this warehouse.")
            else:
                flash("Inventory item added.", "success")
                return redirect(url_for("warehouses.detail", warehouse_id=warehouse.id))
    return _render_detail(warehouse, form), 400


@warehouses_bp.post("/inventory/<int:item_id>/adjust")
@login_required
@roles_required("admin", "staff")
def adjust_inventory(item_id):
    item = db.get_or_404(InventoryItem, item_id)
    try:
        quantity = int((request.form.get("quantity") or "").strip())
        operation = request.form.get("operation", "adjustment")
        expected_version = None
        if operation == "adjustment":
            raw_version = (request.form.get("expected_version") or "").strip()
            if not raw_version.isascii() or not raw_version.isdecimal() or len(raw_version) > 18:
                raise InventoryError("Reload the inventory page before setting the balance.")
            expected_version = int(raw_version)
        change_stock(item, actor_id=current_user.id,
                     operation=operation, expected_version=expected_version,
                     quantity=quantity,
                     reason=request.form.get("reason", "Manual stock adjustment"))
        db.session.commit()
    except (ValueError, InventoryError) as exc:
        db.session.rollback()
        flash(str(exc) if isinstance(exc, InventoryError) else
              "Quantity must be a non-negative whole number.", "danger")
    else:
        flash("Inventory quantity updated.", "success")
    return redirect(url_for("warehouses.detail", warehouse_id=item.warehouse_id))
