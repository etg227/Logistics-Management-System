from flask_wtf import FlaskForm
from wtforms import PasswordField, SelectField, StringField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo, Length


ROLE_OPTIONS = [
    ("admin", "Admin"),
    ("staff", "Staff"),
    ("driver", "Driver"),
    ("customer", "Customer"),
]


class UserDetailsForm(FlaskForm):
    full_name = StringField("Full name", validators=[DataRequired(), Length(min=1, max=100)])
    email = StringField("Email", validators=[DataRequired(), Email(), Length(max=255)])
    role = SelectField("Role", choices=ROLE_OPTIONS, validators=[DataRequired()])
    customer_id = SelectField("Customer account", coerce=int,
                              choices=[(0, "Not linked")], default=0,
                              validate_choice=False, validators=[])
    submit = SubmitField("Save user")


class CreateUserForm(UserDetailsForm):
    password = PasswordField("Temporary password", validators=[DataRequired(), Length(min=8, max=128)])
    confirm_password = PasswordField("Confirm password", validators=[DataRequired(), EqualTo("password", message="Passwords must match.")])
    submit = SubmitField("Create user")


class ResetPasswordForm(FlaskForm):
    password = PasswordField("New password", validators=[DataRequired(), Length(min=8, max=128)])
    confirm_password = PasswordField("Confirm new password", validators=[DataRequired(), EqualTo("password", message="Passwords must match.")])
    submit = SubmitField("Reset password")
