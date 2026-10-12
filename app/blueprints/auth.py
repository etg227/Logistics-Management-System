from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    url_for
)

from flask_login import (
    current_user,
    login_required,
    login_user,
    logout_user
)

from flask_wtf import FlaskForm

from wtforms import (
    PasswordField,
    StringField,
    SubmitField
)

from wtforms.validators import (
    DataRequired,
    Email,
    Length
)

from app.extensions import db
from app.models import User


auth_bp = Blueprint("auth", __name__)


class LoginForm(FlaskForm):
    email = StringField(
        "Email",
        validators=[
            DataRequired(),
            Email(),
            Length(max=255)
        ]
    )

    password = PasswordField(
        "Password",
        validators=[DataRequired()]
    )

    submit = SubmitField("Sign in")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    form = LoginForm()

    if form.validate_on_submit():
        email = form.email.data.strip().lower()

        user = db.session.scalar(
            db.select(User).where(User.email == email)
        )

        if (
            user is not None
            and user.is_active
            and user.check_password(form.password.data)
        ):
            login_user(user)
            return redirect(url_for("main.dashboard"))

        flash("Invalid email or password.", "danger")

    return render_template(
        "auth/login.html",
        form=form
    )


@auth_bp.post("/logout")
@login_required
def logout():
    logout_user()

    flash("You have signed out.", "success")

    return redirect(url_for("auth.login"))