from flask import render_template, request, redirect, url_for, flash, session
from app.db import get_db
from app.routes.staff import staff_bp, login_required, admin_required


def _paginated_query(cursor, base_query, params, page, per_page=15, count_query=None):
    # Create a copy to avoid mutating the caller's dict
    query_params = dict(params)

    if count_query is None:
        count_sql = base_query.strip()
        from_idx = count_sql.upper().find(" FROM ")
        order_idx = count_sql.upper().rfind(" ORDER BY ")
        group_idx = count_sql.upper().rfind(" GROUP BY ")
        end_idx = order_idx if order_idx > 0 else group_idx if group_idx > 0 else len(count_sql)
        count_sql = "SELECT COUNT(*) as total " + count_sql[from_idx:end_idx]
    else:
        count_sql = count_query

    cursor.execute(count_sql, query_params)
    total = cursor.fetchone()["total"]
    pages = (total + per_page - 1) // per_page

    offset = (page - 1) * per_page
    query_params["limit"] = per_page
    query_params["offset"] = offset

    cursor.execute(base_query + " LIMIT %(limit)s OFFSET %(offset)s", query_params)
    items = cursor.fetchall()
    return items, total, pages


@staff_bp.route("/donation-info")
@login_required
@admin_required
def donation_info_list():
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        """
        SELECT d.info_id, d.label, d.content, d.is_image, d.display_order, d.is_active,
               d.created_at, d.updated_at, s.first_name as updated_by_name
        FROM Donation_Info d
        LEFT JOIN Staff s ON d.updated_by = s.staff_id
        ORDER BY d.display_order ASC, d.info_id ASC
        """
    )
    items = cursor.fetchall()
    return render_template("staff_donation_info.html", items=items)


@staff_bp.route("/donation-info/new", methods=["GET", "POST"])
@login_required
@admin_required
def donation_info_new():
    if request.method == "POST":
        label = request.form.get("label", "").strip()
        content = request.form.get("content", "").strip()
        is_image = request.form.get("is_image") == "on"

        try:
            display_order = int(request.form.get("display_order", "0"))
        except ValueError:
            flash("Display order must be a number.", "error")
            return render_template("staff_donation_info_form.html")

        if not label or not content:
            flash("Label and content are required.", "error")
            return render_template("staff_donation_info_form.html")

        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            """
            INSERT INTO Donation_Info (label, content, is_image, display_order, updated_by)
            VALUES (%(label)s, %(content)s, %(is_image)s, %(display_order)s, %(updated_by)s)
            """,
            {
                "label": label,
                "content": content,
                "is_image": is_image,
                "display_order": display_order,
                "updated_by": session["staff_id"],
            },
        )
        db.commit()
        flash("Donation info added.", "success")
        return redirect(url_for("staff.donation_info_list"))

    return render_template("staff_donation_info_form.html", item=None)


@staff_bp.route("/donation-info/<int:info_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def donation_info_edit(info_id):
    db = get_db()
    cursor = db.cursor()

    if request.method == "POST":
        label = request.form.get("label", "").strip()
        content = request.form.get("content", "").strip()
        is_image = request.form.get("is_image") == "on"
        try:
            display_order = int(request.form.get("display_order", "0"))
        except ValueError:
            flash("Display order must be a number.", "error")
            return render_template("staff_donation_info_form.html", item={"info_id": info_id})
        is_active = request.form.get("is_active") == "on"

        if not label or not content:
            flash("Label and content are required.", "error")
            return render_template("staff_donation_info_form.html", item={"info_id": info_id})

        cursor.execute(
            """
            UPDATE Donation_Info
            SET label = %(label)s, content = %(content)s, is_image = %(is_image)s,
                display_order = %(display_order)s, is_active = %(is_active)s, updated_by = %(updated_by)s
            WHERE info_id = %(info_id)s
            """,
            {
                "label": label,
                "content": content,
                "is_image": is_image,
                "display_order": display_order,
                "is_active": is_active,
                "updated_by": session["staff_id"],
                "info_id": info_id,
            },
        )
        db.commit()
        flash("Donation info updated.", "success")
        return redirect(url_for("staff.donation_info_list"))

    cursor.execute(
        "SELECT info_id, label, content, is_image, display_order, is_active FROM Donation_Info WHERE info_id = %(info_id)s",
        {"info_id": info_id},
    )
    item = cursor.fetchone()
    if not item:
        flash("Item not found.", "error")
        return redirect(url_for("staff.donation_info_list"))

    return render_template("staff_donation_info_form.html", item=item)


@staff_bp.route("/donation-info/<int:info_id>/delete", methods=["POST"])
@login_required
@admin_required
def donation_info_delete(info_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("DELETE FROM Donation_Info WHERE info_id = %(info_id)s", {"info_id": info_id})
    db.commit()
    flash("Donation info deleted.", "error")
    return redirect(url_for("staff.donation_info_list"))


@staff_bp.route("/accounts")
@login_required
@admin_required
def accounts():
    db = get_db()
    cursor = db.cursor()

    page = request.args.get("page", 1, type=int)
    per_page = 15

    where_clauses = []
    params = {}

    q = request.args.get("q", "").strip()
    if q:
        where_clauses.append("(username LIKE %(q)s OR first_name LIKE %(q)s OR last_name LIKE %(q)s)")
        params["q"] = f"%{q}%"

    role = request.args.get("role")
    if role:
        where_clauses.append("role = %(role)s")
        params["role"] = role

    status = request.args.get("status")
    if status == "active":
        where_clauses.append("status = TRUE")
    elif status == "inactive":
        where_clauses.append("status = FALSE")

    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

    base_query = f"""
        SELECT staff_id, username, first_name, last_name, role, status
        FROM Staff
        WHERE {where_sql}
        ORDER BY role DESC, staff_id ASC
    """

    staff_list, total, pages = _paginated_query(cursor, base_query, params, page, per_page)
    return render_template("staff_accounts.html", staff_list=staff_list, page=page, pages=pages, total=total)


@staff_bp.route("/accounts/<int:staff_id>/role", methods=["POST"])
@login_required
@admin_required
def change_role(staff_id):
    if staff_id == session["staff_id"]:
        flash("You cannot change your own role.", "error")
        return redirect(url_for("staff.accounts"))

    new_role = request.form.get("role")
    if new_role not in ("admin", "staff"):
        flash("Invalid role.", "error")
        return redirect(url_for("staff.accounts"))

    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        "UPDATE Staff SET role = %(role)s WHERE staff_id = %(staff_id)s",
        {"role": new_role, "staff_id": staff_id},
    )
    db.commit()
    flash(f"Role updated to {new_role}.", "success")
    return redirect(url_for("staff.accounts"))


@staff_bp.route("/accounts/<int:staff_id>/toggle", methods=["POST"])
@login_required
@admin_required
def toggle_status(staff_id):
    db = get_db()
    cursor = db.cursor()

    if staff_id == session["staff_id"]:
        flash("You cannot deactivate your own account.", "error")
        return redirect(url_for("staff.accounts"))

    cursor.execute(
        "SELECT status FROM Staff WHERE staff_id = %(staff_id)s",
        {"staff_id": staff_id},
    )
    row = cursor.fetchone()
    if not row:
        flash("Staff not found.", "error")
        return redirect(url_for("staff.accounts"))

    new_status = not row["status"]
    cursor.execute(
        "UPDATE Staff SET status = %(status)s WHERE staff_id = %(staff_id)s",
        {"status": new_status, "staff_id": staff_id},
    )
    db.commit()

    action = "activated" if new_status else "deactivated"
    flash(f"Account {action}.", "success")
    return redirect(url_for("staff.accounts"))


@staff_bp.route("/animals/<int:animal_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_animal(animal_id):
    db = get_db()
    cursor = db.cursor()

    # Check it exists and isn't already archived
    cursor.execute(
        "SELECT name, is_deleted FROM Animal WHERE animal_id = %(animal_id)s",
        {"animal_id": animal_id},
    )
    row = cursor.fetchone()
    if not row:
        flash("Animal not found.", "error")
        return redirect(url_for("public.animal_list"))
    if row["is_deleted"]:
        flash("Animal is already archived.", "error")
        return redirect(url_for("public.animal_list"))

    # Soft-delete: mark as deleted, keep all records intact
    cursor.execute(
        """
        UPDATE Animal
        SET is_deleted = TRUE,
            deleted_at = NOW(),
            deleted_by = %(staff_id)s
        WHERE animal_id = %(animal_id)s
        """,
        {"staff_id": session["staff_id"], "animal_id": animal_id},
    )
    db.commit()

    flash(f"Animal \"{row['name']}\" has been archived. All adoption/foster/rescue records are preserved.", "success")
    return redirect(url_for("public.animal_list"))