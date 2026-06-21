import os
import secrets
from flask import Flask, request, session, redirect, url_for, flash, render_template
from app.config import Config
from app.db import close_db
from app import cli


def create_app():
    """
    Builds and returns the Flask app. Using a factory function (instead of
    a bare `app = Flask(__name__)` at module level) means we can create
    multiple app instances later if needed (e.g. for testing) and it avoids
    circular-import issues once we have several route files importing
    from each other.
    """
    app = Flask(__name__)
    app.config.from_object(Config)

    # Ensures the DB connection opened during a request is always closed
    # afterward, even if the request raised an error.
    app.teardown_appcontext(close_db)

    # Registers `flask --app run.py init-db`
    cli.init_app(app)

    # CSRF protection (manual, no DB change)
    @app.before_request
    def ensure_csrf_token():
        if "csrf_token" not in session:
            session["csrf_token"] = secrets.token_hex(16)

    @app.before_request
    def csrf_protect():
        if request.method == "POST":
            if "csrf_token" in session:
                form_token = request.form.get("csrf_token")
                if not form_token or form_token != session["csrf_token"]:
                    flash("CSRF token missing or invalid. Please try again.", "error")
                    return redirect(request.referrer or url_for("public.animal_list"))

    @app.context_processor
    def inject_csrf():
        return dict(csrf_token=lambda: session.get("csrf_token", ""))

    # Error handlers
    @app.errorhandler(404)
    def not_found(e):
        return render_template("404.html"), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template("500.html"), 500

    # Register blueprints
    from app.routes.public import public_bp
    app.register_blueprint(public_bp)

    from app.routes.staff import staff_bp
    app.register_blueprint(staff_bp)

    return app