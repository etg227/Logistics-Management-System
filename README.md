# CargoFlow - Logistics Management System

A web-based Logistics Management System developed with
Python, Flask, SQLAlchemy, SQLite, HTML and CSS.

## Tech Stack

- Python 3
- Flask
- Flask-SQLAlchemy
- Flask-Login
- Flask-WTF
- Flask-Migrate
- SQLite
- Jinja2
- pytest

## Installation (Windows PowerShell)

Create a virtual environment:

    python -m venv .venv

Install the dependencies:

    .\.venv\Scripts\python.exe -m pip install -r requirements.txt

Create a `.env` file with a secure SECRET_KEY.

Initialize the database:

    .\.venv\Scripts\python.exe -m flask --app run db init
    .\.venv\Scripts\python.exe -m flask --app run db migrate -m "Initial users table"
    .\.venv\Scripts\python.exe -m flask --app run db upgrade

Create an administrator:

    .\.venv\Scripts\python.exe -m flask --app run create-user --role admin

Run the application:

    .\.venv\Scripts\python.exe run.py

Open http://127.0.0.1:5000

## Testing

    .\.venv\Scripts\python.exe -m pytest -q

## User Roles

- Admin
- Staff
- Driver

## Stage 1

- Flask Application Factory
- Authentication
- Role-Based Access Control
- SQLite Database
- Database Migrations
- Dashboard UI
- Automated Tests

## Future Development

Stage 2:
- Customer Management
- Shipment Management
- Driver Assignment
- Shipment Tracking

Stage 3:
- Dashboard Statistics
- Search and Filtering
- Reports and CSV Export

## Security

Do not commit:
- .env
- SQLite database files
- .venv

This is a local development application, not a
production deployment.