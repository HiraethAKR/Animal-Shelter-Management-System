from functools import wraps
from flask import Blueprint, session, redirect, url_for, flash

staff_bp = Blueprint("staff", __name__, url_prefix="/staff")


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "staff_id" not in session:
            flash("Please log in to access this page.", "error")
            return redirect(url_for("staff.login"))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("staff_role") != "admin":
            flash("Only admins can access this page.", "error")
            return redirect(url_for("staff.applications"))
        return f(*args, **kwargs)
    return decorated_function


def register_staff_routes():
    """Import and register all staff submodules. Called from create_app()."""
    # Import submodules so their routes register on staff_bp
    import app.routes.staff_auth
    import app.routes.staff_dashboard
    import app.routes.staff_admin
    import app.routes.medical