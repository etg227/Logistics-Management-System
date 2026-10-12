import os
from pathlib import Path

import click
from dotenv import load_dotenv
from flask import Flask, render_template
from flask_wtf.csrf import CSRFError

from app.extensions import csrf, db, login_manager, migrate


def create_app(test_config=None):
    project_root = Path(__file__).resolve().parent.parent
    load_dotenv(project_root / ".env")

    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY"),
        SQLALCHEMY_DATABASE_URI=os.environ.get("DATABASE_URL", "sqlite:///logistics.db"),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )
    if test_config is not None:
        app.config.update(test_config)
    if not app.config["SECRET_KEY"]:
        raise RuntimeError("Missing SECRET_KEY. Create a .env file.")

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    migrate.init_app(app, db)

    from app.models import User, Customer, Shipment, ShipmentEvent  # noqa: F401
    from app.blueprints.auth import auth_bp
    from app.blueprints.main import main_bp
    from app.blueprints.customers import customers_bp
    from app.blueprints.shipments import shipments_bp
    from app.blueprints.tracking import tracking_bp
    from app.blueprints.admin_users import admin_users_bp

    for blueprint in (auth_bp, main_bp, customers_bp, shipments_bp, tracking_bp, admin_users_bp):
        app.register_blueprint(blueprint)

    @login_manager.user_loader
    def load_user(user_id):
        try:
            user = db.session.get(User, int(user_id))
        except (TypeError, ValueError):
            return None
        if user is not None and user.is_active:
            return user
        return None

    @app.cli.command("create-user")
    @click.option("--role", type=click.Choice(["admin", "staff", "driver"]), prompt=True)
    @click.option("--email", prompt=True)
    @click.option("--name", "full_name", prompt="Full name")
    @click.password_option(confirmation_prompt=True)
    def create_user(role, email, full_name, password):
        email = email.strip().lower()
        full_name = full_name.strip()
        if not email or not full_name:
            raise click.ClickException("Email and name are required.")
        if len(password) < 8:
            raise click.ClickException("Password must be at least 8 characters.")
        existing = db.session.scalar(db.select(User).where(User.email == email))
        if existing:
            raise click.ClickException("This email already exists.")
        user = User(role=role, email=email, full_name=full_name)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo(f"Created {role} account: {email}")

    @app.errorhandler(403)
    def forbidden(error):
        return render_template("errors/error.html", code=403,
                               message="You do not have permission to view this page."), 403

    @app.errorhandler(404)
    def not_found(error):
        return render_template("errors/error.html", code=404,
                               message="The requested page could not be found."), 404

    @app.errorhandler(500)
    def server_error(error):
        db.session.rollback()
        return render_template("errors/error.html", code=500,
                               message="Something went wrong. Please try again."), 500

    @app.errorhandler(CSRFError)
    def csrf_error(error):
        return render_template("errors/error.html", code=400,
                               message="Invalid form token. Refresh the page."), 400

    return app
