import json
import csv
import io
from datetime import date
from flask import render_template, request, redirect, url_for, flash, session, Response
from app.db import get_db
from app.routes.staff import staff_bp, login_required, admin_required
from app.routes.public import _save_animal_image
from app.services.edit_apply import apply_animal_edit, EDIT_HANDLERS


def _paginated_query(cursor, base_query, params, page, per_page=15, count_query=None):
    if count_query is None:
        count_sql = base_query.strip()
        from_idx = count_sql.upper().find(" FROM ")
        order_idx = count_sql.upper().rfind(" ORDER BY ")
        group_idx = count_sql.upper().rfind(" GROUP BY ")
        end_idx = order_idx if order_idx > 0 else group_idx if group_idx > 0 else len(count_sql)
        count_sql = "SELECT COUNT(*) as total " + count_sql[from_idx:end_idx]
    else:
        count_sql = count_query

    cursor.execute(count_sql, params)
    total = cursor.fetchone()["total"]
    pages = (total + per_page - 1) // per_page

    offset = (page - 1) * per_page
    params["limit"] = per_page
    params["offset"] = offset

    cursor.execute(base_query + " LIMIT %(limit)s OFFSET %(offset)s", params)
    items = cursor.fetchall()
    return items, total, pages


def _get_current_record(cursor, table_name, record_id):
    if not record_id:
        return None
    if table_name == "Animal":
        cursor.execute("SELECT * FROM Animal WHERE animal_id = %(id)s", {"id": record_id})
    elif table_name == "Vet":
        cursor.execute("SELECT * FROM Vet WHERE vet_id = %(id)s", {"id": record_id})
    elif table_name == "Medical_Record":
        cursor.execute("SELECT * FROM Medical_Record WHERE record_id = %(id)s", {"id": record_id})
    elif table_name == "Treatment":
        cursor.execute("SELECT * FROM Treatment WHERE treatment_id = %(id)s", {"id": record_id})
    else:
        return None
    return cursor.fetchone()


@staff_bp.route("/dashboard")
@login_required
def dashboard():
    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT COUNT(*) as total FROM Animal")
    total_animals = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) as total FROM Animal WHERE status = 'available'")
    available_animals = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) as total FROM Edit_Request WHERE status = 'pending'")
    pending_tickets = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) as total FROM Rescue WHERE status = 'pending'")
    pending_rescues = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) as total FROM Adoption WHERE status = 'pending'")
    pending_adoptions = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) as total FROM Foster WHERE status = 'pending'")
    pending_fosters = cursor.fetchone()["total"]

    cursor.execute("SELECT COUNT(*) as total FROM Staff WHERE status = FALSE")
    pending_staff = cursor.fetchone()["total"]

    cursor.execute(
        """
        SELECT record_id, table_name, record_type, submitted_at
        FROM Edit_Request
        WHERE status = 'pending'
        ORDER BY submitted_at DESC
        LIMIT 5
        """
    )
    recent_tickets = cursor.fetchall()

    return render_template(
        "staff_dashboard.html",
        total_animals=total_animals,
        available_animals=available_animals,
        pending_tickets=pending_tickets,
        pending_rescues=pending_rescues,
        pending_adoptions=pending_adoptions,
        pending_fosters=pending_fosters,
        pending_staff=pending_staff,
        recent_tickets=recent_tickets,
    )


@staff_bp.route("/tickets")
@login_required
@admin_required
def tickets():
    db = get_db()
    cursor = db.cursor()

    page = request.args.get("page", 1, type=int)
    per_page = 15

    where_clauses = ["status = 'pending'"]
    params = {}

    table_name = request.args.get("table_name")
    if table_name:
        where_clauses.append("table_name = %(table_name)s")
        params["table_name"] = table_name

    record_type = request.args.get("record_type")
    if record_type:
        where_clauses.append("record_type = %(record_type)s")
        params["record_type"] = record_type

    q = request.args.get("q", "").strip()
    if q:
        where_clauses.append("field_changes LIKE %(q)s")
        params["q"] = f"%{q}%"

    where_sql = " AND ".join(where_clauses)

    base_query = f"""
        SELECT record_id, table_name, record_type, request_id, field_changes, submitted_at
        FROM Edit_Request
        WHERE {where_sql}
        ORDER BY submitted_at DESC
    """

    requests, total, pages = _paginated_query(cursor, base_query, params, page, per_page)

    for req in requests:
        req["fields"] = json.loads(req["field_changes"])
        req["current"] = None
        if req["record_type"] == "update" and req.get("request_id"):
            req["current"] = _get_current_record(cursor, req["table_name"], req["request_id"])

    return render_template("staff_tickets.html", requests=requests, page=page, pages=pages, total=total)


@staff_bp.route("/tickets/<int:record_id>/approve", methods=["POST"])
@login_required
@admin_required
def approve_ticket(record_id):
    db = get_db()
    cursor = db.cursor()

    cursor.execute(
        "SELECT table_name, record_type, request_id, field_changes, status FROM Edit_Request WHERE record_id = %(record_id)s",
        {"record_id": record_id},
    )
    row = cursor.fetchone()

    if not row:
        flash("Request not found.", "error")
        return redirect(url_for("staff.tickets"))

    if row["status"] != "pending":
        flash(f"This request has already been {row['status']}.", "error")
        return redirect(url_for("staff.tickets"))

    field_changes = json.loads(row["field_changes"])

    handler = EDIT_HANDLERS.get(row["table_name"], {}).get(row["record_type"])

    if handler is None:
        flash("This table/record type combination is not supported.", "error")
        return redirect(url_for("staff.tickets"))

    try:
        new_id = handler(row["record_type"], row.get("request_id"), field_changes)
    except RuntimeError as e:
        flash(str(e), "error")
        return redirect(url_for("staff.tickets"))

    cursor.execute(
        """
        UPDATE Edit_Request
        SET status = 'approved', reviewed_at = NOW(), reviewed_by = %(staff_id)s
        WHERE record_id = %(record_id)s
        """,
        {"staff_id": session["staff_id"], "record_id": record_id},
    )
    db.commit()

    flash(f"Approved! New ID: {new_id}" if row["record_type"] == "create" else f"Approved update for {row['table_name']} ID: {new_id}", "success")
    return redirect(url_for("staff.tickets"))


@staff_bp.route("/tickets/<int:record_id>/reject", methods=["POST"])
@login_required
@admin_required
def reject_ticket(record_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        """
        UPDATE Edit_Request
        SET status = 'rejected', reviewed_at = NOW(), reviewed_by = %(staff_id)s
        WHERE record_id = %(record_id)s
        """,
        {"staff_id": session["staff_id"], "record_id": record_id},
    )
    db.commit()

    flash("Request rejected.", "error")
    return redirect(url_for("staff.tickets"))


@staff_bp.route("/applications")
@login_required
def applications():
    db = get_db()
    cursor = db.cursor()

    page = request.args.get("page", 1, type=int)
    per_page = 15
    q = request.args.get("q", "").strip()
    status_filter = request.args.get("status", "pending")

    name_filter = ""
    params = {}
    if q:
        name_filter = " AND (p.first_name LIKE %(q)s OR p.last_name LIKE %(q)s)"
        params["q"] = f"%{q}%"

    status_clause = ""
    if status_filter == "pending":
        status_clause = " AND r.status = 'pending'"
    elif status_filter == "approved":
        status_clause = " AND r.status = 'approved'"
    elif status_filter == "rejected":
        status_clause = " AND r.status = 'rejected'"

    base_rescues = f"""
        SELECT r.rescue_id, r.person_id, r.rescue_date, r.location, r.notes, r.submitted_at, r.animal_id,
               r.animal_species, r.photo_url, r.status,
               p.first_name, p.last_name
        FROM Rescue r
        JOIN Person p ON r.person_id = p.person_id
        WHERE 1=1 {status_clause} {name_filter}
        ORDER BY r.submitted_at ASC
    """
    rescues, total_rescues, pages_rescues = _paginated_query(cursor, base_rescues, params.copy(), page, per_page)

    for rescue in rescues:
        cursor.execute(
            "SELECT contact_type, contact_value FROM Person_Contact WHERE person_id = %(person_id)s",
            {"person_id": rescue["person_id"]},
        )
        rescue["contacts"] = cursor.fetchall()

    status_clause = ""
    if status_filter == "pending":
        status_clause = " AND a.status = 'pending'"
    elif status_filter == "approved":
        status_clause = " AND a.status = 'approved'"
    elif status_filter == "rejected":
        status_clause = " AND a.status = 'rejected'"

    base_adoptions = f"""
        SELECT a.adoption_id, a.person_id, a.animal_id, a.submitted_at, a.status,
               p.first_name, p.last_name,
               an.name as animal_name, an.species, an.breed
        FROM Adoption a
        JOIN Person p ON a.person_id = p.person_id
        JOIN Animal an ON a.animal_id = an.animal_id
        WHERE 1=1 {status_clause} {name_filter}
        ORDER BY a.submitted_at ASC
    """
    adoptions, total_adoptions, pages_adoptions = _paginated_query(cursor, base_adoptions, params.copy(), page, per_page)

    for adoption in adoptions:
        cursor.execute(
            "SELECT contact_type, contact_value FROM Person_Contact WHERE person_id = %(person_id)s",
            {"person_id": adoption["person_id"]},
        )
        adoption["contacts"] = cursor.fetchall()

    status_clause = ""
    if status_filter == "pending":
        status_clause = " AND f.status = 'pending'"
    elif status_filter == "approved":
        status_clause = " AND f.status = 'approved'"
    elif status_filter == "rejected":
        status_clause = " AND f.status = 'rejected'"

    base_fosters = f"""
        SELECT f.foster_id, f.person_id, f.animal_id, f.start_date, f.end_date, f.notes, f.submitted_at, f.status,
               p.first_name, p.last_name,
               an.name as animal_name, an.species, an.breed
        FROM Foster f
        JOIN Person p ON f.person_id = p.person_id
        JOIN Animal an ON f.animal_id = an.animal_id
        WHERE 1=1 {status_clause} {name_filter}
        ORDER BY f.submitted_at ASC
    """
    fosters, total_fosters, pages_fosters = _paginated_query(cursor, base_fosters, params.copy(), page, per_page)

    for foster in fosters:
        cursor.execute(
            "SELECT contact_type, contact_value FROM Person_Contact WHERE person_id = %(person_id)s",
            {"person_id": foster["person_id"]},
        )
        foster["contacts"] = cursor.fetchall()

    total = total_rescues + total_adoptions + total_fosters
    pages = max(pages_rescues, pages_adoptions, pages_fosters)

    return render_template("staff_applications.html", rescues=rescues, adoptions=adoptions, fosters=fosters, page=page, pages=pages, total=total, status_filter=status_filter)


@staff_bp.route("/applications/rescue/<int:rescue_id>/verify", methods=["POST"])
@login_required
def verify_rescue(rescue_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        "UPDATE Rescue SET status = 'approved', reviewed_by = %(staff_id)s WHERE rescue_id = %(rescue_id)s AND status = 'pending'",
        {"staff_id": session["staff_id"], "rescue_id": rescue_id},
    )
    db.commit()
    flash("Rescue report verified.", "success")
    return redirect(url_for("staff.applications"))


@staff_bp.route("/applications/rescue/<int:rescue_id>/reject", methods=["POST"])
@login_required
def reject_rescue(rescue_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        "UPDATE Rescue SET status = 'rejected', reviewed_by = %(staff_id)s WHERE rescue_id = %(rescue_id)s AND status = 'pending'",
        {"staff_id": session["staff_id"], "rescue_id": rescue_id},
    )
    db.commit()
    flash("Rescue report rejected.", "error")
    return redirect(url_for("staff.applications"))


@staff_bp.route("/applications/adoption/<int:adoption_id>/verify", methods=["POST"])
@login_required
def verify_adoption(adoption_id):
    db = get_db()
    cursor = db.cursor()

    cursor.execute(
        """
        UPDATE Adoption
        SET status = 'approved', adoption_date = CURDATE(), reviewed_by = %(staff_id)s
        WHERE adoption_id = %(adoption_id)s AND status = 'pending'
        """,
        {"staff_id": session["staff_id"], "adoption_id": adoption_id},
    )

    cursor.execute(
        """
        UPDATE Animal
        SET status = 'adopted'
        WHERE animal_id = (SELECT animal_id FROM Adoption WHERE adoption_id = %(adoption_id)s)
        """,
        {"adoption_id": adoption_id},
    )

    db.commit()
    flash("Adoption verified! Animal marked as adopted.", "success")
    return redirect(url_for("staff.applications"))


@staff_bp.route("/applications/adoption/<int:adoption_id>/reject", methods=["POST"])
@login_required
def reject_adoption(adoption_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        "UPDATE Adoption SET status = 'rejected', reviewed_by = %(staff_id)s WHERE adoption_id = %(adoption_id)s AND status = 'pending'",
        {"staff_id": session["staff_id"], "adoption_id": adoption_id},
    )
    db.commit()
    flash("Adoption rejected.", "error")
    return redirect(url_for("staff.applications"))


@staff_bp.route("/applications/foster/<int:foster_id>/verify", methods=["POST"])
@login_required
def verify_foster(foster_id):
    db = get_db()
    cursor = db.cursor()

    cursor.execute(
        """
        UPDATE Foster
        SET status = 'approved', reviewed_by = %(staff_id)s
        WHERE foster_id = %(foster_id)s AND status = 'pending'
        """,
        {"staff_id": session["staff_id"], "foster_id": foster_id},
    )

    cursor.execute(
        """
        UPDATE Animal
        SET status = 'fostered'
        WHERE animal_id = (SELECT animal_id FROM Foster WHERE foster_id = %(foster_id)s)
        """,
        {"foster_id": foster_id},
    )

    db.commit()
    flash("Foster verified! Animal marked as fostered.", "success")
    return redirect(url_for("staff.applications"))


@staff_bp.route("/applications/foster/<int:foster_id>/reject", methods=["POST"])
@login_required
def reject_foster(foster_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        "UPDATE Foster SET status = 'rejected', reviewed_by = %(staff_id)s WHERE foster_id = %(foster_id)s AND status = 'pending'",
        {"staff_id": session["staff_id"], "foster_id": foster_id},
    )
    db.commit()
    flash("Foster rejected.", "error")
    return redirect(url_for("staff.applications"))


@staff_bp.route("/applications/rescue/<int:rescue_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_rescue(rescue_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("DELETE FROM Rescue WHERE rescue_id = %(rescue_id)s", {"rescue_id": rescue_id})
    db.commit()
    flash("Rescue record deleted.", "error")
    return redirect(url_for("staff.applications"))


@staff_bp.route("/applications/adoption/<int:adoption_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_adoption(adoption_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        "SELECT animal_id, status FROM Adoption WHERE adoption_id = %(adoption_id)s",
        {"adoption_id": adoption_id},
    )
    row = cursor.fetchone()
    if row and row["status"] == "approved":
        cursor.execute(
            "UPDATE Animal SET status = 'available' WHERE animal_id = %(animal_id)s",
            {"animal_id": row["animal_id"]},
        )
    cursor.execute("DELETE FROM Adoption WHERE adoption_id = %(adoption_id)s", {"adoption_id": adoption_id})
    db.commit()
    flash("Adoption record deleted. Animal reverted to available if previously adopted.", "error")
    return redirect(url_for("staff.applications"))


@staff_bp.route("/applications/foster/<int:foster_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_foster(foster_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        "SELECT animal_id, status FROM Foster WHERE foster_id = %(foster_id)s",
        {"foster_id": foster_id},
    )
    row = cursor.fetchone()
    if row and row["status"] == "approved":
        cursor.execute(
            "UPDATE Animal SET status = 'available' WHERE animal_id = %(animal_id)s",
            {"animal_id": row["animal_id"]},
        )
    cursor.execute("DELETE FROM Foster WHERE foster_id = %(foster_id)s", {"foster_id": foster_id})
    db.commit()
    flash("Foster record deleted. Animal reverted to available if previously fostered.", "error")
    return redirect(url_for("staff.applications"))


@staff_bp.route("/applications/rescue/<int:rescue_id>/link", methods=["GET", "POST"])
@login_required
def link_rescue_animal(rescue_id):
    db = get_db()
    cursor = db.cursor()

    cursor.execute(
        """
        SELECT r.rescue_id, r.person_id, r.location, r.notes, r.animal_id,
               p.first_name, p.last_name
        FROM Rescue r
        JOIN Person p ON r.person_id = p.person_id
        WHERE r.rescue_id = %(rescue_id)s
        """,
        {"rescue_id": rescue_id},
    )
    rescue = cursor.fetchone()

    if not rescue:
        flash("Rescue report not found.", "error")
        return redirect(url_for("staff.applications"))

    if rescue["animal_id"]:
        flash("This rescue is already linked to an animal.", "info")
        return redirect(url_for("staff.applications"))

    cursor.execute(
        "SELECT animal_id, name, species, breed, status FROM Animal ORDER BY name"
    )
    animals = cursor.fetchall()

    if request.method == "POST":
        action = request.form.get("action")

        if action == "existing":
            animal_id = request.form.get("animal_id")
            if not animal_id:
                flash("Please select an animal.", "error")
                return render_template("staff_link_rescue.html", rescue=rescue, animals=animals)

            cursor.execute(
                "UPDATE Rescue SET animal_id = %(animal_id)s WHERE rescue_id = %(rescue_id)s",
                {"animal_id": int(animal_id), "rescue_id": rescue_id},
            )
            db.commit()
            flash("Rescue linked to existing animal.", "success")
            return redirect(url_for("staff.applications"))

        elif action == "new":
            name = request.form.get("name", "").strip()
            species = request.form.get("species", "")
            breed = request.form.get("breed", "").strip()
            sex = request.form.get("sex", "")
            birth_date = request.form.get("birth_date", "") or None
            notes = request.form.get("notes", "") or None

            if not name or not species or not sex:
                flash("Name, species, and sex are required.", "error")
                return render_template("staff_link_rescue.html", rescue=rescue, animals=animals)

            field_changes = {
                "name": name,
                "species": species,
                "breed": breed or None,
                "sex": sex,
                "birth_date": birth_date,
                "status": "available",
                "notes": notes,
            }

            if session.get("staff_role") == "admin":
                new_animal_id = apply_animal_edit("create", None, field_changes)
                cursor.execute(
                    "UPDATE Rescue SET animal_id = %(animal_id)s WHERE rescue_id = %(rescue_id)s",
                    {"animal_id": new_animal_id, "rescue_id": rescue_id},
                )
                db.commit()
                flash(f"New animal created (ID: {new_animal_id}) and linked to rescue.", "success")
                return redirect(url_for("staff.applications"))
            else:
                cursor.execute(
                    """
                    INSERT INTO Edit_Request (table_name, record_type, field_changes, status)
                    VALUES (%(table_name)s, %(record_type)s, %(field_changes)s, 'pending')
                    """,
                    {
                        "table_name": "Animal",
                        "record_type": "create",
                        "field_changes": json.dumps(field_changes),
                    },
                )
                db.commit()
                flash("Animal creation request submitted for admin approval.", "success")
                return redirect(url_for("staff.applications"))

    return render_template("staff_link_rescue.html", rescue=rescue, animals=animals)


@staff_bp.route("/applications/rescue/<int:rescue_id>/verify-create", methods=["GET", "POST"])
@login_required
@admin_required
def verify_rescue_create_animal(rescue_id):
    db = get_db()
    cursor = db.cursor()

    cursor.execute(
        """
        SELECT r.rescue_id, r.person_id, r.location, r.notes, r.animal_id,
               r.animal_species, r.photo_url,
               p.first_name, p.last_name
        FROM Rescue r
        JOIN Person p ON r.person_id = p.person_id
        WHERE r.rescue_id = %(rescue_id)s
        """,
        {"rescue_id": rescue_id},
    )
    rescue = cursor.fetchone()

    if not rescue:
        flash("Rescue report not found.", "error")
        return redirect(url_for("staff.applications"))

    if rescue["animal_id"]:
        flash("This rescue is already linked to an animal.", "info")
        return redirect(url_for("staff.applications"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        species = request.form.get("species", "")
        breed = request.form.get("breed", "").strip()
        sex = request.form.get("sex", "")
        birth_date = request.form.get("birth_date", "") or None
        notes = request.form.get("notes", "") or None

        if not name or not species or not sex:
            flash("Name, species, and sex are required.", "error")
            return render_template("staff_verify_rescue_create.html", rescue=rescue)

        if request.files.get("image") and request.files.get("image").filename:
            try:
                image_url = _save_animal_image(request.files.get("image"))
            except ValueError as e:
                flash(str(e), "error")
                return render_template("staff_verify_rescue_create.html", rescue=rescue)
        else:
            image_url = rescue.get("photo_url")

        field_changes = {
            "name": name,
            "species": species,
            "breed": breed or None,
            "sex": sex,
            "birth_date": birth_date,
            "status": "available",
            "notes": notes,
            "image_url": image_url,
        }

        new_animal_id = apply_animal_edit("create", None, field_changes)

        cursor.execute(
            """
            UPDATE Rescue
            SET animal_id = %(animal_id)s, status = 'approved', reviewed_by = %(staff_id)s
            WHERE rescue_id = %(rescue_id)s
            """,
            {
                "animal_id": new_animal_id,
                "staff_id": session["staff_id"],
                "rescue_id": rescue_id,
            },
        )
        db.commit()
        flash(f"Rescue verified and animal created (ID: {new_animal_id}).", "success")
        return redirect(url_for("staff.applications"))

    return render_template("staff_verify_rescue_create.html", rescue=rescue)


@staff_bp.route("/animals/export")
@login_required
@admin_required
def export_animals_csv():
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        "SELECT animal_id, name, species, breed, sex, birth_date, status, notes FROM Animal ORDER BY name"
    )
    animals = cursor.fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Name", "Species", "Breed", "Sex", "Birth Date", "Status", "Notes"])

    for a in animals:
        writer.writerow([
            a["animal_id"],
            a["name"],
            a["species"],
            a["breed"] or "",
            a["sex"],
            a["birth_date"] or "",
            a["status"],
            a["notes"] or "",
        ])

    csv_data = output.getvalue()
    output.close()

    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=animals.csv"},
    )