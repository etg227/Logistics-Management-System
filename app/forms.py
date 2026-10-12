from flask_wtf import FlaskForm
from wtforms import FloatField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Email, Length, NumberRange, Optional


class CustomerForm(FlaskForm):
    name = StringField("Customer name", validators=[DataRequired(), Length(max=120)])
    email = StringField("Email (optional)", validators=[Optional(), Email(), Length(max=255)])
    phone = StringField("Phone", validators=[DataRequired(), Length(max=40)])
    address = StringField("Address", validators=[DataRequired(), Length(max=255)])
    submit = SubmitField("Save Customer")


class ShipmentForm(FlaskForm):
    customer_id = SelectField("Sender / Customer", coerce=int, validators=[DataRequired()])
    recipient_name = StringField("Recipient name", validators=[DataRequired(), Length(max=120)])
    recipient_phone = StringField("Recipient phone", validators=[DataRequired(), Length(max=40)])
    origin = StringField("Pickup address", validators=[DataRequired(), Length(max=255)])
    destination = StringField("Delivery address", validators=[DataRequired(), Length(max=255)])
    description = TextAreaField("Package description", validators=[Optional(), Length(max=300)])
    weight_kg = FloatField("Weight (kg)", validators=[DataRequired(), NumberRange(min=0.01, max=100000)])
    submit = SubmitField("Save Shipment")