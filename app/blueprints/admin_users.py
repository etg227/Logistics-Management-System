from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError

from app.admin_forms import CreateUserForm, ResetPasswordForm, UserDetailsForm
from app.extensions import db
from app.models import Customer, User
from app.permissions import roles_required
from app.services.user_management import (
    UserManagementError, email_taken, normalize_email, validate_user_change,
)

admin_users_bp = Blueprint("admin_users", __name__, url_prefix="/admin/users")


@admin_users_bp.get("/")
@login_required
@roles_required("admin")
def index():
    search = request.args.get("q", "").strip()[:100]
    role = request.args.get("role", "").strip().lower()
    status = request.args.get("status", "").strip().lower()
    stmt = db.select(User)
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(or_(User.full_name.ilike(pattern), User.email.ilike(pattern)))
    if role in {"admin", "staff", "driver", "customer"}:
        stmt = stmt.where(User.role == role)
    if status == "active":
        stmt = stmt.where(User.is_active.is_(True))
    elif status == "inactive":
        stmt = stmt.where(User.is_active.is_(False))
    pagination = db.paginate(
        stmt.order_by(User.id.desc()),
        page=request.args.get("page", 1, type=int), per_page=10, error_out=False,
    )
    return render_template("admin/users/index.html", pagination=pagination,
                           q=search, role=role, status=status)


@admin_users_bp.route("/new", methods=["GET", "POST"])
@login_required
@roles_required("admin")
def create():
    form = CreateUserForm()
    form.customer_id.choices = [(0, "Not linked")] + [(c.id, f"{c.name} (#{c.id})") for c in
                                db.session.scalars(db.select(Customer).where(Customer.active.is_(True)).order_by(Customer.name)).all()]
    if form.validate_on_submit():
        email = normalize_email(form.email.data)
        full_name = form.full_name.data.strip()
        if not full_name:
            form.full_name.errors.append("Please enter a name.")
        elif email_taken(email):
            form.email.errors.append("This email is already registered.")
        elif form.role.data == "customer" and not form.customer_id.data:
            form.customer_id.errors.append("Select the customer this account belongs to.")
        elif form.role.data == "customer" and db.session.get(Customer, form.customer_id.data) is None:
            form.customer_id.errors.append("Select an existing customer record.")
        else:
            user = User(full_name=full_name, email=email, role=form.role.data, is_active=True,
                        customer_id=form.customer_id.data if form.role.data == "customer" else None)
            user.set_password(form.password.data)
            db.session.add(user)
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                form.email.errors.append("This email is already registered.")
            else:
                flash("User created successfully.", "success")
                return redirect(url_for("admin_users.detail", user_id=user.id))
    return render_template("admin/users/form.html", form=form, title="Add User", creating=True)


@admin_users_bp.get("/<int:user_id>")
@login_required
@roles_required("admin")
def detail(user_id):
    user = db.get_or_404(User, user_id)
    return render_template("admin/users/detail.html", user=user)


@admin_users_bp.route("/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
@roles_required("admin")
def edit(user_id):
    user = db.get_or_404(User, user_id)
    form = UserDetailsForm(obj=user)
    form.customer_id.choices = [(0, "Not linked")] + [(c.id, f"{c.name} (#{c.id})") for c in
                                db.session.scalars(db.select(Customer).order_by(Customer.name)).all()]
    if form.validate_on_submit():
        email = normalize_email(form.email.data)
        full_name = form.full_name.data.strip()
        if not full_name:
            form.full_name.errors.append("Please enter a name.")
        elif email_taken(email, except_user_id=user.id):
            form.email.errors.append("This email is already registered.")
        elif form.role.data == "customer" and not form.customer_id.data:
            form.customer_id.errors.append("Select the customer this account belongs to.")
        elif form.role.data == "customer" and db.session.get(Customer, form.customer_id.data) is None:
            form.customer_id.errors.append("Select an existing customer record.")
        else:
            try:
                user.customer_id = form.customer_id.data if form.role.data == "customer" else None
                validate_user_change(user, current_user, new_role=form.role.data)
            except UserManagementError as exc:
                form.role.errors.append(str(exc))
            else:
                user.full_name = full_name
                user.email = email
                user.role = form.role.data
                try:
                    db.session.commit()
                except IntegrityError:
                    db.session.rollback()
                    form.email.errors.append("This email is already registered.")
                else:
                    flash("User details updated.", "success")
                    return redirect(url_for("admin_users.detail", user_id=user.id))
    return render_template("admin/users/form.html", form=form, title="Edit User", creating=False, user=user)


@admin_users_bp.post("/<int:user_id>/toggle")
@login_required
@roles_required("admin")
def toggle(user_id):
    user = db.get_or_404(User, user_id)
    try:
        validate_user_change(user, current_user, new_active=not user.is_active)
    except UserManagementError as exc:
        flash(str(exc), "danger")
    else:
        user.is_active = not user.is_active
        db.session.commit()
        flash("User account status updated.", "success")
    return redirect(url_for("admin_users.detail", user_id=user_id))


@admin_users_bp.route("/<int:user_id>/reset-password", methods=["GET", "POST"])
@login_required
@roles_required("admin")
def reset_password(user_id):
    user = db.get_or_404(User, user_id)
    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        db.session.commit()
        flash("User password updated.", "success")
        return redirect(url_for("admin_users.detail", user_id=user.id))
    return render_template("admin/users/reset_password.html", user=user, form=form)
