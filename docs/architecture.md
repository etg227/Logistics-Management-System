# CargoFlow - Architecture and Requirements

## Architecture

- Presentation: Jinja2 templates, CSS and Flask-WTF forms.
- Web controllers: Flask Blueprints (`auth`, `main`, `customers`, `shipments`, `tracking`).
- Business rules: `app/services/shipment_service.py`.
- Data persistence: Flask-SQLAlchemy models and Alembic migrations (SQLite).
- Authentication: Flask-Login; login session and CSRF validation.
- Extensions: warehouse/inventory records, in-app notifications, customer portal accounts and invoices.

## User roles and permissions

| Operation | Admin | Staff | Driver | Customer | Public |
|---|---|---|---|---|---|
| Dashboard | Yes | Yes | Yes (own shipments) | Portal | No |
| Create and update customers | Yes | Yes | No | No | No |
| Create and edit pending shipments | Yes | Yes | No | No | No |
| Assign active drivers | Yes | Yes | No | No | No |
| Cancel pre-pickup shipments | Yes | Yes | No | No | No |
| See internal shipment details | Yes | Yes | Own deliveries only | Own shipments | No |
| Advance assigned delivery | No | No | Own deliveries only | No | No |
| View tracking status timeline | Yes | Yes | Yes | Own shipments | Yes (with tracking number) |
| Customer portal, own shipments and invoices | No | No | No | Own records only | No |
| Warehouse and inventory management | Yes | Yes | No | No | No |
| Issue and reconcile invoices | Yes | Yes | No | View own invoices | No |
| In-app notifications | Yes | Yes | Yes | Own notifications | No |

## Core entities

- `User`: sign-in credentials and role (`admin`, `staff`, `driver`, `customer`); customer portal users link to `Customer`.
- `Customer`: sender details and active/inactive state.
- `Shipment`: tracking number, sender, recipient, addresses, weight, assigned driver and current status.
- `ShipmentEvent`: immutable event row generated on creation, assignment, status change or cancellation.

Relationships: `Customer 1 -- n Shipment`, `Customer 1 -- n Invoice`, `Customer 1 -- n User(customer portal)`, `User(driver) 1 -- n Shipment`, `Shipment 1 -- n ShipmentEvent`.

## Delivery workflow

`Pending -> Assigned -> Picked Up -> In Transit -> Out for Delivery -> Delivered`

Only `Pending` and `Assigned` can become `Cancelled`; driver assignment and reassignment are only allowed before pickup. A driver can only advance the next valid state for an assigned shipment. Terminal shipments cannot be reopened.

## Functional requirements

- FR01: Authenticated users can access role-specific pages.
- FR02: Admin and Staff can maintain customer records without deleting associated shipment history.
- FR03: Admin and Staff can create shipments with automatically generated unique tracking numbers.
- FR04: Admin and Staff can edit shipment details while the status is Pending.
- FR05: Admin and Staff can assign an active Driver before pickup.
- FR06: Assigned Drivers can advance shipment status exactly one step at a time.
- FR07: Every workflow transition records actor, status, timestamp and internal note.
- FR08: The public tracking page shows status and timestamps but does not show customer or recipient personal details.
- FR09: Shipment lists support server-side search, filters and pagination.
- FR10: Dashboard totals reflect persistent database records and a driver's own assignments only.

## Non-functional requirements

- NFR01: All state-changing operations use POST forms with CSRF validation.
- NFR02: Authorization is enforced in controllers and business rules, not only through hidden navigation links.
- NFR03: Passwords are stored as password hashes; `.env` and SQLite databases are excluded from Git.
- NFR04: Automated regression tests cover authentication, validation, permissions, workflow and tracking privacy.

## Extension entities

- `Warehouse` and `InventoryItem`: storage locations and stock quantities with reorder thresholds.
- `Notification`: user-scoped in-app messages, optionally linked to a shipment.
- `Invoice`: customer billing record with optional shipment link, surcharge, tax, due date and paid status.
- Customer portal users have role `customer` and a required `customer_id`; portal queries are always scoped to that customer.
