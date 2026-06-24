import bcrypt
from flask import render_template, request, redirect, url_for, flash, session
from app.db import get_db
from app.routes.staff import staff_bp, login_required, admin_required


@staff_bp.route("/bootstrap", methods=["GET", "POST"])
def bootstrap():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT COUNT(*) as count FROM Staff")
    result = cursor.fetchone()

    if result and result["count"] > 0:
        flash("Admin account already exists. Please log in.", "info")
        return redirect(url_for("staff.login"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()

        if not first_name or not last_name:
            flash("First and last name are required.", "error")
            return render_template("staff_bootstrap.html")

        password = request.form.get("password")

        if not username:
            flash("Username is required.", "error")
            return render_template("staff_bootstrap.html")

        if not password or len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
            return render_template("staff_bootstrap.html")

        cursor.execute(
            "SELECT staff_id FROM Staff WHERE username = %(username)s",
            {"username": username},
        )
        if cursor.fetchone():
            flash("That username is already taken.", "error")
            return render_template("staff_bootstrap.html")

        hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())

        cursor.execute(
            """
            INSERT INTO Staff (username, first_name, last_name, role, status, password)
            VALUES (%(username)s, %(first_name)s, %(last_name)s, 'admin', TRUE, %(password)s)
            """,
            {
                "username": username,
                "first_name": first_name,
                "last_name": last_name,
                "password": hashed.decode("utf-8"),
            },
        )
        db.commit()

        flash(f"Admin account created! Username: {username}. Please log in.", "success")
        return redirect(url_for("staff.login"))

    return render_template("staff_bootstrap.html")


@staff_bp.route("/register", methods=["GET", "POST"])
def register():
    db = get_db()
    cursor = db.cursor()

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()

        if not first_name or not last_name:
            flash("First and last name are required.", "error")
            return render_template("staff_register.html")

        password = request.form.get("password")
        confirm_password = request.form.get("confirm_password")

        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return render_template("staff_register.html")

        if not username:
            flash("Username is required.", "error")
            return render_template("staff_register.html")

        if not password or len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
            return render_template("staff_register.html")

        cursor.execute(
            "SELECT staff_id FROM Staff WHERE username = %(username)s",
            {"username": username},
        )
        if cursor.fetchone():
            flash("That username is already taken.", "error")
            return render_template("staff_register.html")

        hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())

        cursor.execute(
            """
            INSERT INTO Staff (username, first_name, last_name, role, status, password)
            VALUES (%(username)s, %(first_name)s, %(last_name)s, 'staff', FALSE, %(password)s)
            """,
            {
                "username": username,
                "first_name": first_name,
                "last_name": last_name,
                "password": hashed.decode("utf-8"),
            },
        )
        db.commit()

        flash("Account created! An admin must approve it before you can log in.", "success")
        return redirect(url_for("staff.login"))

    return render_template("staff_register.html")


@staff_bp.route("/login", methods=["GET", "POST"])
def login():
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT COUNT(*) as count FROM Staff")
    result = cursor.fetchone()

    if result and result["count"] == 0:
        return redirect(url_for("staff.bootstrap"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password")

        cursor.execute(
            "SELECT staff_id, first_name, password, role, status FROM Staff WHERE username = %(username)s",
            {"username": username},
        )
        user = cursor.fetchone()

        if not user or not bcrypt.checkpw(password.encode("utf-8"), user["password"].encode("utf-8")):
            flash("Invalid username or password.", "error")
            return render_template("staff_login.html")

        if not user["status"]:
            flash("Your account is pending admin approval.", "error")
            return render_template("staff_login.html")

        session["staff_id"] = user["staff_id"]
        session["staff_name"] = user["first_name"]
        session["staff_role"] = user["role"]
        flash(f"Welcome, {user['first_name']}!", "success")
        return redirect(url_for("staff.dashboard"))

    return render_template("staff_login.html")


@staff_bp.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("public.animal_list"))


@staff_bp.route("/pending")
@login_required
@admin_required
def pending_staff():
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        """
        SELECT staff_id, username, first_name, last_name, role
        FROM Staff
        WHERE status = FALSE
        ORDER BY staff_id
        """
    )
    pending = cursor.fetchall()
    return render_template("staff_pending.html", pending=pending)


@staff_bp.route("/pending/<int:staff_id>/approve", methods=["POST"])
@login_required
@admin_required
def approve_staff(staff_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        "UPDATE Staff SET status = TRUE WHERE staff_id = %(staff_id)s",
        {"staff_id": staff_id},
    )
    db.commit()
    flash("Staff account approved.", "success")
    return redirect(url_for("staff.pending_staff"))


@staff_bp.route("/pending/<int:staff_id>/reject", methods=["POST"])
@login_required
@admin_required
def reject_staff(staff_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        "DELETE FROM Staff WHERE staff_id = %(staff_id)s AND status = FALSE",
        {"staff_id": staff_id},
    )
    db.commit()
    flash("Staff registration rejected.", "error")
    return redirect(url_for("staff.pending_staff"))


@staff_bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    db = get_db()
    cursor = db.cursor()

    if request.method == "POST":
        current = request.form.get("current_password", "")
        new_pass = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")

        cursor.execute(
            "SELECT password FROM Staff WHERE staff_id = %(staff_id)s",
            {"staff_id": session["staff_id"]},
        )
        row = cursor.fetchone()

        if not bcrypt.checkpw(current.encode("utf-8"), row["password"].encode("utf-8")):
            flash("Current password is incorrect.", "error")
            return render_template("staff_change_password.html")

        if len(new_pass) < 8:
            flash("New password must be at least 8 characters.", "error")
            return render_template("staff_change_password.html")

        if new_pass != confirm:
            flash("New passwords do not match.", "error")
            return render_template("staff_change_password.html")

        hashed = bcrypt.hashpw(new_pass.encode("utf-8"), bcrypt.gensalt())
        cursor.execute(
            "UPDATE Staff SET password = %(password)s WHERE staff_id = %(staff_id)s",
            {"password": hashed.decode("utf-8"), "staff_id": session["staff_id"]},
        )
        db.commit()

        flash("Password updated successfully.", "success")
        return redirect(url_for("staff.dashboard"))

    return render_template("staff_change_password.html")