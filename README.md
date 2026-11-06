## 🚀 Getting started

You need Python 3.10 or newer and Git.

### 1. Clone the repository

Clone it into a normal folder, **not** inside iCloud Drive, OneDrive or Dropbox. Sync tools can damage the `.git` folder.

```bash
git clone https://github.com/etg227/Logistics-Management-System.git
cd Logistics-Management-System
```

### 2. Create a virtual environment and install packages

**Windows (PowerShell)**
```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

**macOS / Linux**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Open `.env` and replace the `SECRET_KEY` value with a random string. You can generate one with:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 3. Create the database and an admin account

```bash
flask --app run db upgrade
flask --app run create-user --role admin
```

`create-user` asks for an email, a name and a password (at least 8 characters).

> ⚠️ **Only run `db upgrade`.** Do **not** run `flask db init` (the `migrations/` folder already exists) or `flask db migrate` unless your task changes a model. See [Changing the database](#changing-the-database).

Optional: load demo data so the pages are not empty while you click around.

```bash
python scripts/seed_demo.py                  # three staff/driver accounts, 8 workflow + 7 report demo shipments
python scripts/seed_demo.py --reset-passwords
```

New seeded accounts use the password `demo12345`. Existing passwords are kept
unless `--reset-passwords` is supplied. The script never creates an admin account
— use `create-user` above for that. It is safe to re-run: it only adds what is
missing and keeps existing shipment dates, statuses and tracking numbers.

#### Report demo data

The **DEMO Report Acceptance** customer has seven synthetic shipment snapshots.
Recipient names begin with `DEMO`; newly created tracking numbers begin with
`DEMO-RPT-`. Driver 1 is `driver@example.com` (Chan Tai Man), and Driver 2 is
`driver2@example.com` (Leung Mei Mei).

Dates below are relative to the **first seed run's UTC date**:

| Demo suffix | Status | Expected delivery | Created | Driver |
|---|---|---|---|---|
| LATE-A | Assigned | Yesterday | Today | 1 |
| LATE-B | Assigned | Two days ago | Today | 2 |
| OLD-LATE-A | Assigned | Yesterday | Seven days ago | 1 |
| TODAY-A | Assigned | Today | Today | 1 |
| FUTURE | Pending | Tomorrow | Today | Unassigned |
| ON-TIME | Delivered | Today; delivered today | Today | 1 |
| LATE-DONE | Delivered | Yesterday; delivered today | Today | 2 |

To check report filters, sign in as Admin or Staff and open **Reports**:

1. On the first seed date, **Overdue only** includes the three LATE-A, LATE-B and
   OLD-LATE-A fixtures. Due-today and delivered fixtures are excluded.
2. Select Driver 1, status **Assigned**, and set **From (UTC)** and **To (UTC)**
   to the first seed date. These fields filter the shipment's creation date.
3. Click **Overdue Shipments**. The filters should remain selected and the demo
   results should contain only LATE-A. **Download CSV** should keep that scope.

Other existing shipments may also match the filters. Re-running the seed does
not refresh demo dates: due-today shipments can become overdue on later days.
The snapshots are labelled demo data, not reconstructed delivery history.

### 4. Run the app

```bash
flask --app run run --debug --port 5001
```

Open http://127.0.0.1:5001 and sign in with the admin account. With `--debug`, the server reloads when you save a file.

We use port 5001 because macOS uses port 5000 for AirPlay Receiver.

### 5. Run the tests

```bash
pytest -q
```

Run this with the project virtual environment active (Git Bash: `source .venv/Scripts/activate`,
cmd: `.venv\Scripts\activate`, PowerShell: `.venv\Scripts\Activate.ps1`). Without it you will see
`ModuleNotFoundError: No module named 'app'` or `flask` — that is the venv, not the code.
`pytest.ini` already puts the repo root on `sys.path`, so no `PYTHONPATH` tweak is needed.

All tests must pass before you open a pull request.

---

## 🤝 How we work

### Every time you start working

```bash
git checkout main
git pull
pip install -r requirements.txt   # in case someone added a package
flask --app run db upgrade        # in case someone added a migration
```

### Working on a task

1. **Create a branch** named after your task:
   ```bash
   git checkout -b T01-warehouse-model
   ```
2. **Write the code and the tests**, then run `pytest -q`.
3. **Commit with your own GitHub account**, with a clear message:
   ```bash
   git add .
   git commit -m "T01: add Warehouse model and list page"
   git push -u origin T01-warehouse-model
   ```
4. **Open a pull request** on GitHub into `main`. Mention the task ID in the title.
5. **Another member reviews** it. After approval, merge it, and update the task board status.

### Rules

- **Never push directly to `main`.** Always use a branch and a pull request.
- **Use your own GitHub account.** Check with `git config user.name` and `git config user.email`. Commits made from someone else's account do not count as your contribution.
- **One task per branch.** Keep pull requests small, so they are easy to review.
- **Never commit** `.env`, `.venv/`, `instance/` or `*.db` files. `.gitignore` already excludes them.

### Changing the database

If your task adds or changes a model in `app/models/`:

```bash
flask --app run db migrate -m "Add warehouse table"
flask --app run db upgrade
```

Commit the new file in `migrations/versions/` together with your model change. Tell the group in your pull request, so everyone runs `db upgrade` after pulling.

### Definition of Done

A task is done when:
1. It works in the browser for every role that should use it, and is blocked for roles that should not.
2. It has automated tests, and `pytest -q` passes.
3. Any new page is reachable from the navigation.
4. Another member has reviewed and approved the pull request.
5. The task board in this README is updated.

---

## 👥 Roles and permissions

| Operation | Admin | Staff | Driver | Customer | Public |
|---|---|---|---|---|---|
| Dashboard | ✓ | ✓ | Own shipments | | |
| Manage customers | ✓ | ✓ | | | |
| Create and edit pending shipments | ✓ | ✓ | | | |
| Assign drivers, resolve failed deliveries, cancel | ✓ | ✓ | | | |
| Update delivery status | | | Own shipments | | |
| Reports and CSV export | ✓ | ✓ | | | |
| Manage user accounts | ✓ | | | | |
| Track a parcel by tracking number | ✓ | ✓ | ✓ | ✓ | ✓ |
| Customer portal (own shipments and invoices) | | | | Own records | |

## 🗂️ Project structure

```
app/
├── __init__.py          create_app(): config, extensions, blueprints, CLI commands
├── extensions.py        db, login manager, CSRF, migrations
├── permissions.py       @roles_required(...)
├── forms.py             customer and shipment forms
├── admin_forms.py       user management forms
├── models/              User, Customer, Shipment, ShipmentEvent, Warehouse, InventoryItem, Notification, Invoice
├── services/            business rules (shipment workflow, analytics, user management)
├── blueprints/          routes: auth, main, customers, shipments, tracking, admin_users, reports, warehouses, notifications, portal, invoices
├── templates/           Jinja2 pages, one folder per blueprint
└── static/css/          stylesheets
migrations/              database migrations (Flask-Migrate / Alembic)
tests/                   pytest tests
docs/architecture.md     architecture and requirements notes
run.py                   entry point
```

Business rules belong in `app/services/`, not in the routes. For example, all shipment status changes go through `app/services/shipment_service.py`, which checks the rules and records a `ShipmentEvent`.

## 🔒 Security notes

- Passwords are stored as hashes. All forms that change data use POST with CSRF protection.
- Permissions are checked on the server in every route, not only by hiding links.
- `.env` and database files are never committed.
- This is a local development application, not a production deployment.

## Current product extensions

The current development branch also includes the following MVP modules:

- **Warehouse management:** administrators and staff can create warehouses, add inventory items, adjust quantities and see reorder warnings.
- **In-app notifications:** shipment status changes and new invoices create notifications for linked customer accounts and assigned drivers. Users can mark notifications read.
- **Customer portal:** a customer account is linked to a customer record and can see only its own shipments, invoices and recent updates at `/portal/`.
- **Billing:** administrators and staff can issue one invoice per shipment or a general customer invoice, record surcharge/tax, and mark invoices as paid.

Run `flask --app run db upgrade` after pulling these changes. To create a portal account, an administrator adds a user with role **Customer** and links it to an existing customer record.
