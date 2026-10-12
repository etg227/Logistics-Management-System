from flask_wtf import FlaskForm
from wtforms import (DateField, FloatField, SelectField, StringField,
                     SubmitField, TextAreaField)
from wtforms.validators import DataRequired, Email, Length, NumberRange, Optional

from app.models.shipment import PACKAGE_TYPES


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
    package_type = SelectField("Package type", choices=list(PACKAGE_TYPES.items()), default="parcel", validators=[Optional()])
    length_cm = FloatField("Length (cm)", validators=[Optional(), NumberRange(min=0.01, max=100000)])
    width_cm = FloatField("Width (cm)", validators=[Optional(), NumberRange(min=0.01, max=100000)])
    height_cm = FloatField("Height (cm)", validators=[Optional(), NumberRange(min=0.01, max=100000)])
    delivery_instructions = TextAreaField("Delivery instructions", validators=[Optional(), Length(max=300)])
    expected_delivery_date = DateField("Expected delivery date", validators=[Optional()], format="%Y-%m-%d")
    submit = SubmitField("Save Shipment")
