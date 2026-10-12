# System Architecture

## Architecture Style

Layered Flask web application.

## Presentation Layer

Jinja2 templates and CSS.

## Application Layer

Flask Blueprints:
- auth
- main

## Business Logic

- Login verification
- Password hashing
- Role-based permission checking

## Data Layer

Flask-SQLAlchemy with SQLite.

## User Roles

Admin, Staff, Driver.

## Security Controls

- Password hashing
- Session authentication
- CSRF protection
- Server-side authorization
- No public administrator registration

## Testing

pytest with an isolated in-memory SQLite database.

## Planned Evolution

The application will be extended with customers,
shipments, driver assignments and tracking events.