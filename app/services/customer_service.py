"""Customer management business rules."""
from app.extensions import db
from app.models import Customer

def create_customer(*, name, email, phone, address):
    customer = Customer(
        name=name.strip(),
        email=(email or "").strip().lower() or None,
        phone=phone.strip(),
        address=address.strip(),
    )
    db.session.add(customer)
    db.session.commit()
    return customer

def update_customer(customer, *, name, email, phone, address):
    customer.name = name.strip()
    customer.email = (email or "").strip().lower() or None
    customer.phone = phone.strip()
    customer.address = address.strip()
    db.session.commit()
    return customer

def toggle_customer_status(customer):
    customer.active = not customer.active
    db.session.commit()
    return customer