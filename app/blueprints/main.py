from flask import (
    Blueprint,
    redirect,
    render_template,
    url_for
)

from flask_login import (
    current_user,
    login_required
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
    return render_template("main/dashboard.html")


@main_bp.get("/admin")
@login_required
@roles_required("admin")
def admin():
    return render_template(
        "main/role_page.html",
        title="Administration",
        role="Admin"
    )


@main_bp.get("/driver")
@login_required
@roles_required("driver")
def driver():
    return render_template(
        "main/role_page.html",
        title="Driver Portal",
        role="Driver"
    )