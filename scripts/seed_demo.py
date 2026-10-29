"""Seed a local development database with demo users and shipments.

Usage (from the repo root):

    .venv/Scripts/python.exe scripts/seed_demo.py                 # add anything missing
    .venv/Scripts/python.exe scripts/seed_demo.py --reset-passwords

Safe to re-run: existing users are kept, existing demo shipments are not
duplicated (it checks for the demo customers first).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import Customer, Shipment, User  # noqa: E402
from app.models.shipment import (  # noqa: E402
    IN_TRANSIT, OUT_FOR_DELIVERY, PICKED_UP,
)
from app.services.shipment_service import (  # noqa: E402
    advance_delivery, assign_driver, create_shipment, mark_delivery_failed,
    resolve_failed_delivery,
)

DEMO_PASSWORD = "demo12345"

USERS = [
    ("Ops Coordinator", "staff@example.com", "staff"),
    ("Chan Tai Man", "driver@example.com", "driver"),
    ("Leung Mei Mei", "driver2@example.com", "driver"),
]

CUSTOMERS = [
    ("Bright Harbour Ltd", "91234567", "Unit 1203, 88 Queen's Road Central, Central", "ops@brightharbour.example"),
    ("Green Leaf Foods", "92345678", "17/F, 2 Nathan Road, Tsim Sha Tsui", "logistics@greenleaf.example"),
    ("Summit Tools Co", "93456789", "G/F, 9 On King Street, Sha Tin", "shop@summit.example"),
]


def ensure_user(email: str, full_name: str, role: str, reset: bool) -> User:
    user = db.session.scalar(db.select(User).where(User.email == email))
    if user is None:
        user = User(full_name=full_name, email=email, role=role)
        user.set_password(DEMO_PASSWORD)
        user.is_active = True
        db.session.add(user)
        db.session.commit()
    elif reset:
        user.set_password(DEMO_PASSWORD)
        user.is_active = True
        db.session.commit()
    return user


def ensure_customer(name: str, phone: str, address: str, email: str) -> Customer:
    customer = db.session.scalar(db.select(Customer).where(Customer.name == name))
    if customer is None:
        customer = Customer(name=name, phone=phone, address=address, email=email)
        db.session.add(customer)
        db.session.commit()
    return customer


def shipment_exists(recipient: str) -> bool:
    return db.session.scalar(
        db.select(db.func.count(Shipment.id)).where(Shipment.recipient_name == recipient)
    ) > 0


CHAIN = [PICKED_UP, IN_TRANSIT, OUT_FOR_DELIVERY]


def make_shipment(*, customer, actor, recipient, phone, destination, driver,
                  target="assigned", received_by=None, failure_reason=None,
                  failure_note=""):
    """Drive one shipment to `target` through the real service functions."""
    if shipment_exists(recipient):
        return None
    shipment = create_shipment(
        customer_id=customer.id, created_by_id=actor.id,
        recipient_name=recipient, recipient_phone=phone,
        origin="Kwun Tong Depot", destination=destination,
        description="Assorted cartons", weight_kg=4.5,
    )
    if driver is not None:
        assign_driver(shipment, driver, actor.id)
        stop_at = len(CHAIN) - 1 if target in ("delivered", "delivery_failed") else CHAIN.index(target)
        for step in CHAIN[: stop_at + 1]:
            advance_delivery(shipment, step, driver.id)
        if target == "delivered":
            advance_delivery(shipment, "delivered", driver.id, received_by=received_by or recipient)
        elif target == "delivery_failed":
            mark_delivery_failed(shipment, driver.id, reason=failure_reason,
                                 note=failure_note, location=destination)
    return shipment


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset-passwords", action="store_true",
                        help="reset the demo accounts back to the demo password")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        db.create_all()

        users = {email: ensure_user(email, name, role, args.reset_passwords)
                 for name, email, role in USERS}
        staff = db.session.scalar(db.select(User).where(User.email == "staff@example.com"))
        driver = users["driver@example.com"]
        driver2 = users["driver2@example.com"]
        admin = db.session.scalar(db.select(User).where(User.role == "admin"))

        customers = [ensure_customer(*row) for row in CUSTOMERS]

        created = []

        def add(**kwargs):
            shipment = make_shipment(actor=staff, **kwargs)
            if shipment is not None:
                created.append(shipment.tracking_number)

        # Driver 1 worklist
        add(customer=customers[0], recipient="Wong Siu Ming", phone="61112233",
            destination="Central, Queen's Road 88", driver=driver, target="assigned")
        add(customer=customers[1], recipient="Lee Ka Yan", phone="62223344",
            destination="Tsim Sha Tsui, Nathan Road 2", driver=driver, target=PICKED_UP)
        add(customer=customers[2], recipient="Ho Wing Chi", phone="63334455",
            destination="Sha Tin, 12 On King Street", driver=driver, target=IN_TRANSIT)
        add(customer=customers[0], recipient="Cheung Mei Ling", phone="64445566",
            destination="Kwun Tong, 5 Hoi Bun Road", driver=driver,
            target=OUT_FOR_DELIVERY)
        add(customer=customers[1], recipient="Ng Chun Ho", phone="65556677",
            destination="Mong Kok, 33 Argyle Street", driver=driver,
            target="delivered", received_by="Clerk at front desk")
        add(customer=customers[2], recipient="Tam Wai Yin", phone="66667788",
            destination="Sham Shui Po, 8 Fuk Wing Street", driver=driver,
            target="delivery_failed", failure_reason="recipient_unavailable",
            failure_note="Left a call-me card")

        # Another driver's booking — must never appear on Chan Tai Man's worklist
        add(customer=customers[0], recipient="Kuai Po Sin", phone="67776666",
            destination="Causeway Bay, 22 Yee Wo Street", driver=driver2, target=PICKED_UP)

        # Unassigned work for the staff dashboard
        pending = make_shipment(
            customer=customers[1], actor=staff, recipient="Unassigned Booking",
            phone="68887777", destination="Tsuen Wan, 1 Sai Lau Kok Road", driver=None,
        )
        if pending is not None:
            created.append(pending.tracking_number)

        for shipment in db.session.scalars(db.select(Shipment)).all():
            pass  # touch the session so relationships are available to the printout

        total = db.session.scalar(db.select(db.func.count(Shipment.id))) or 0
        print(f"Users ready: admin={admin.email if admin else 'MISSING'}, "
              f"staff@example.com, driver@example.com, driver2@example.com")
        print(f"Demo password for new/--reset accounts: {DEMO_PASSWORD}")
        print(f"Shipments in database: {total} (created this run: {len(created)})")
        print("Driver login -> http://127.0.0.1:5001/driver  (driver@example.com)")


if __name__ == "__main__":
    main()
