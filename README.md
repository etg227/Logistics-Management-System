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
python scripts/seed_demo.py                  # three staff/driver accounts, eight shipments covering every status
python scripts/seed_demo.py --reset-passwords
```

The seeded accounts use the password `demo12345`. The script never creates an
admin account — use `create-user` above for that. It is safe to re-run: it only
adds what is missing.

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

| Operation | Admin | Staff | Driver | Public |
|---|---|---|---|---|
| Dashboard | ✓ | ✓ | Own shipments | |
| Manage customers | ✓ | ✓ | | |
| Create and edit pending shipments | ✓ | ✓ | | |
| Assign drivers, resolve failed deliveries, cancel | ✓ | ✓ | | |
| Update delivery status | | | Own shipments | |
| Reports and CSV export | ✓ | ✓ | | |
| Manage user accounts | ✓ | | | |
| Track a parcel by tracking number | ✓ | ✓ | ✓ | ✓ |

## 🗂️ Project structure

```
app/
├── __init__.py          create_app(): config, extensions, blueprints, CLI commands
├── extensions.py        db, login manager, CSRF, migrations
├── permissions.py       @roles_required(...)
├── forms.py             customer and shipment forms
├── admin_forms.py       user management forms
├── models/              User, Customer, Shipment, ShipmentEvent
├── services/            business rules (shipment workflow, analytics, user management)
├── blueprints/          routes: auth, main, customers, shipments, tracking, admin_users, reports
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
