"""Self-service account settings, available to every signed-in role."""
from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.forms import ChangePasswordForm

profile_bp = Blueprint("profile", __name__, url_prefix="/profile")


@profile_bp.route("/password", methods=["GET", "POST"])
@login_required
def change_password():
    form = ChangePasswordForm()

    if form.validate_on_submit():
        current_password = form.current_password.data

        if not current_user.check_password(current_password):
            form.current_password.errors.append("Current password is incorrect.")
        elif current_password == form.password.data:
            form.password.errors.append(
                "Your new password must be different from the current one."
            )
        else:
            current_user.set_password(form.password.data)
            db.session.commit()
            flash("Your password has been updated.", "success")
            return redirect(url_for("main.dashboard"))

    return render_template("profile/change_password.html", form=form)
