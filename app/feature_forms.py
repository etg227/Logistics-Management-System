from flask_wtf import FlaskForm
from wtforms import DateField, FloatField, IntegerField, SelectField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length, NumberRange, Optional


class WarehouseForm(FlaskForm):
    name = StringField("Warehouse name", validators=[DataRequired(), Length(max=120)])
    location = StringField("Location", validators=[DataRequired(), Length(max=255)])
    capacity = IntegerField("Capacity", validators=[DataRequired(), NumberRange(min=0, max=100000000)])
    submit = SubmitField("Save warehouse")


class InventoryItemForm(FlaskForm):
    sku = StringField("SKU", validators=[DataRequired(), Length(max=60)])
    name = StringField("Item name", validators=[DataRequired(), Length(max=120)])
    quantity = IntegerField("Quantity", validators=[DataRequired(), NumberRange(min=0, max=100000000)])
    reorder_level = IntegerField("Reorder level", validators=[DataRequired(), NumberRange(min=0, max=100000000)])
    unit = StringField("Unit", default="units", validators=[DataRequired(), Length(max=30)])
    submit = SubmitField("Save inventory")


class InvoiceForm(FlaskForm):
    customer_id = SelectField("Customer", coerce=int, validators=[DataRequired()])
    shipment_id = SelectField("Shipment (optional)", coerce=int, validators=[Optional()])
    subtotal = FloatField("Subtotal", validators=[DataRequired(), NumberRange(min=0, max=100000000)])
    surcharge = FloatField("Surcharge", default=0, validators=[Optional(), NumberRange(min=0, max=100000000)])
    tax = FloatField("Tax", default=0, validators=[Optional(), NumberRange(min=0, max=100000000)])
    due_date = DateField("Due date", validators=[Optional()], format="%Y-%m-%d")
    notes = TextAreaField("Notes", validators=[Optional(), Length(max=500)])
    submit = SubmitField("Issue invoice")
