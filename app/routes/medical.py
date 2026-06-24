import json
from datetime import date
from flask import render_template, request, redirect, url_for, flash, session
from app.db import get_db
from app.routes.staff import staff_bp, login_required, admin_required
from app.routes.public import _validate_contacts
from app.services.edit_apply import apply_vet_edit, apply_medical_record_edit, apply_treatment_edit


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


@staff_bp.route("/vets")
@login_required
def vet_list():
    db = get_db()
    cursor = db.cursor()

    page = request.args.get("page", 1, type=int)
    per_page = 15

    where_clauses = []
    params = {}

    q = request.args.get("q", "").strip()
    if q:
        where_clauses.append("(v.first_name LIKE %(q)s OR v.last_name LIKE %(q)s OR v.affiliation LIKE %(q)s)")
        params["q"] = f"%{q}%"

    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

    base_query = f"""
        SELECT v.vet_id, v.first_name, v.last_name, v.affiliation,
               GROUP_CONCAT(CONCAT(vc.contact_type, ': ', vc.contact_value) SEPARATOR ', ') as contacts
        FROM Vet v
        LEFT JOIN Vet_Contact vc ON v.vet_id = vc.vet_id
        WHERE {where_sql}
        GROUP BY v.vet_id
        ORDER BY v.last_name, v.first_name
    """

    count_query = f"""
        SELECT COUNT(DISTINCT v.vet_id) as total
        FROM Vet v
        LEFT JOIN Vet_Contact vc ON v.vet_id = vc.vet_id
        WHERE {where_sql}
    """

    vets, total, pages = _paginated_query(cursor, base_query, params, page, per_page, count_query)
    return render_template("staff_vets.html", vets=vets, page=page, pages=pages, total=total)


@staff_bp.route("/vets/new", methods=["GET", "POST"])
@login_required
def vet_new():
    if request.method == "POST":
        first_name = request.form.get("first_name", "").strip()
        last_name = request.form.get("last_name", "").strip()
        affiliation = request.form.get("affiliation", "").strip()
        contact_types = request.form.getlist("contact_type[]")
        contact_values = request.form.getlist("contact_value[]")

        if not first_name or not last_name:
            flash("First and last name are required.", "error")
            return render_template("staff_vet_form.html",
                form_data={"first_name": first_name, "last_name": last_name, "affiliation": affiliation},
                contacts=list(zip(contact_types, contact_values))
                )

        contacts = []
        for ct, cv in zip(contact_types, contact_values):
            cv = cv.strip()
            if ct and cv:
                contacts.append({"contact_type": ct, "contact_value": cv})

        validation_errors = _validate_contacts(contact_types, contact_values)
        if validation_errors:
            for err in validation_errors:
                flash(err, "error")
            return render_template("staff_vet_form.html", 
            form_data={"first_name": first_name, "last_name": last_name, "affiliation": affiliation},
            contacts=list(zip(contact_types, contact_values))
            )

        field_changes = {
            "first_name": first_name,
            "last_name": last_name,
            "affiliation": affiliation or None,
            "contacts": contacts,
        }

        db = get_db()
        cursor = db.cursor()

        if session.get("staff_role") == "admin":
            new_id = apply_vet_edit("create", None, field_changes)
            db.commit()
            flash(f"Vet created (ID: {new_id}).", "success")
            return redirect(url_for("staff.vet_list"))

        cursor.execute(
            """
            INSERT INTO Edit_Request (table_name, record_type, field_changes, status)
            VALUES (%(table_name)s, %(record_type)s, %(field_changes)s, 'pending')
            """,
            {
                "table_name": "Vet",
                "record_type": "create",
                "field_changes": json.dumps(field_changes),
            },
        )
        db.commit()

        flash("Vet creation request submitted for admin approval.", "success")
        return redirect(url_for("staff.vet_list"))

    return render_template("staff_vet_form.html")


@staff_bp.route("/vets/<int:vet_id>/edit", methods=["GET", "POST"])
@login_required
def vet_edit_request(vet_id):
    db = get_db()
    cursor = db.cursor()

    cursor.execute(
        "SELECT vet_id, first_name, last_name, affiliation FROM Vet WHERE vet_id = %(vet_id)s",
        {"vet_id": vet_id},
    )
    vet = cursor.fetchone()

    if not vet:
        flash("Vet not found.", "error")
        return redirect(url_for("staff.vet_list"))

    cursor.execute(
        "SELECT contact_type, contact_value FROM Vet_Contact WHERE vet_id = %(vet_id)s",
        {"vet_id": vet_id},
    )
    vet["contacts"] = cursor.fetchall()

    if request.method == "POST":
        field_changes = {}
        new_first = request.form.get("first_name", "").strip()
        new_last = request.form.get("last_name", "").strip()
        new_affil = request.form.get("affiliation", "").strip()

        if new_first and new_first != vet["first_name"]:
            field_changes["first_name"] = new_first
        if new_last and new_last != vet["last_name"]:
            field_changes["last_name"] = new_last
        if new_affil != (vet["affiliation"] or ""):
            field_changes["affiliation"] = new_affil or None

        contact_types = request.form.getlist("contact_type[]")
        contact_values = request.form.getlist("contact_value[]")

        validation_errors = _validate_contacts(contact_types, contact_values)
        if validation_errors:
            for err in validation_errors:
                flash(err, "error")
            vet["first_name"] = new_first or vet["first_name"]
            vet["last_name"] = new_last or vet["last_name"]
            vet["affiliation"] = new_affil or vet["affiliation"]
            vet["contacts"] = [{"contact_type": ct, "contact_value": cv} 
                            for ct, cv in zip(contact_types, contact_values)]
            return render_template("staff_vet_edit_form.html", vet=vet)

        new_contacts = []
        for ct, cv in zip(contact_types, contact_values):
            cv = cv.strip()
            if ct and cv:
                new_contacts.append({"contact_type": ct, "contact_value": cv})

        old_contacts = [{"contact_type": c["contact_type"], "contact_value": c["contact_value"]} for c in vet["contacts"]]
        if new_contacts != old_contacts:
            field_changes["contacts"] = new_contacts

        if not field_changes:
            flash("No changes detected.", "info")
            return redirect(url_for("staff.vet_list"))

        if session.get("staff_role") == "admin":
            apply_vet_edit("update", vet_id, field_changes)
            db.commit()
            flash("Vet updated.", "success")
            return redirect(url_for("staff.vet_list"))

        cursor.execute(
            """
            INSERT INTO Edit_Request (table_name, record_type, request_id, field_changes, status)
            VALUES (%(table_name)s, %(record_type)s, %(request_id)s, %(field_changes)s, 'pending')
            """,
            {
                "table_name": "Vet",
                "record_type": "update",
                "request_id": vet_id,
                "field_changes": json.dumps(field_changes),
            },
        )
        db.commit()

        flash("Vet edit request submitted for admin approval.", "success")
        return redirect(url_for("staff.vet_list"))

    return render_template("staff_vet_edit_form.html", vet=vet)


@staff_bp.route("/vets/<int:vet_id>/delete", methods=["POST"])
@login_required
@admin_required
def vet_delete(vet_id):
    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT COUNT(*) as count FROM Treatment WHERE vet_id = %(vet_id)s", {"vet_id": vet_id})
    result = cursor.fetchone()

    if result and result["count"] > 0:
        flash("Cannot delete vet: referenced by existing treatments.", "error")
        return redirect(url_for("staff.vet_list"))

    cursor.execute("DELETE FROM Vet_Contact WHERE vet_id = %(vet_id)s", {"vet_id": vet_id})
    cursor.execute("DELETE FROM Vet WHERE vet_id = %(vet_id)s", {"vet_id": vet_id})
    db.commit()

    flash("Vet deleted.", "error")
    return redirect(url_for("staff.vet_list"))


@staff_bp.route("/medical-records")
@login_required
def medical_record_list():
    db = get_db()
    cursor = db.cursor()

    page = request.args.get("page", 1, type=int)
    per_page = 15

    where_clauses = []
    params = {}

    q = request.args.get("q", "").strip()
    if q:
        where_clauses.append("a.name LIKE %(q)s")
        params["q"] = f"%{q}%"

    date_from = request.args.get("date_from")
    if date_from:
        where_clauses.append("mr.visit_date >= %(date_from)s")
        params["date_from"] = date_from

    date_to = request.args.get("date_to")
    if date_to:
        where_clauses.append("mr.visit_date <= %(date_to)s")
        params["date_to"] = date_to

    outcome = request.args.get("outcome")
    if outcome:
        where_clauses.append("mr.outcome LIKE %(outcome)s")
        params["outcome"] = f"%{outcome}%"

    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

    sort = request.args.get("sort", "date_desc")
    if sort == "date_asc":
        order_by = "mr.visit_date ASC"
    elif sort == "animal":
        order_by = "a.name ASC"
    else:
        order_by = "mr.visit_date DESC"

    base_query = f"""
        SELECT mr.record_id, mr.animal_id, mr.visit_date, mr.outcome,
               a.name as animal_name
        FROM Medical_Record mr
        JOIN Animal a ON mr.animal_id = a.animal_id
        WHERE {where_sql}
        ORDER BY {order_by}
    """

    records, total, pages = _paginated_query(cursor, base_query, params, page, per_page)
    return render_template("staff_medical_records.html", records=records, page=page, pages=pages, total=total)


@staff_bp.route("/medical-records/propose", methods=["GET", "POST"])
@staff_bp.route("/medical-records/propose/<int:animal_id>", methods=["GET", "POST"])
@login_required
def propose_medical_record(animal_id=None):
    db = get_db()
    cursor = db.cursor()
    cursor.execute("SELECT animal_id, name FROM Animal ORDER BY name")
    animals = cursor.fetchall()

    if request.method == "POST":
        animal_id = request.form.get("animal_id")
        visit_date = request.form.get("visit_date")
        outcome = request.form.get("outcome", "").strip()

        if not all([animal_id, visit_date]):
            flash("Animal and visit date are required.", "error")
            return render_template("staff_propose_medical_record.html", animals=animals, preselected_animal_id=animal_id)

        try:
            visit = date.fromisoformat(visit_date)
            if visit > date.today():
                flash("Visit date cannot be in the future.", "error")
                return render_template("staff_propose_medical_record.html", animals=animals, preselected_animal_id=animal_id)
        except ValueError:
            flash("Invalid visit date format.", "error")
            return render_template("staff_propose_medical_record.html", animals=animals, preselected_animal_id=animal_id)

        field_changes = {
            "animal_id": int(animal_id),
            "visit_date": visit_date,
            "outcome": outcome or None,
        }

        if session.get("staff_role") == "admin":
            new_id = apply_medical_record_edit("create", None, field_changes)
            db.commit()
            flash(f"Medical record created (ID: {new_id}).", "success")
            next_url = request.args.get('next')
            if next_url:
                return redirect(next_url)
            return redirect(url_for("staff.medical_record_list"))

        cursor.execute(
            """
            INSERT INTO Edit_Request (table_name, record_type, field_changes, status)
            VALUES (%(table_name)s, %(record_type)s, %(field_changes)s, 'pending')
            """,
            {
                "table_name": "Medical_Record",
                "record_type": "create",
                "field_changes": json.dumps(field_changes),
            },
        )
        db.commit()

        flash("Medical record proposal submitted for admin approval.", "success")
        next_url = request.args.get('next')
        if next_url:
            return redirect(next_url)
        return redirect(url_for("staff.medical_record_list"))

    return render_template("staff_propose_medical_record.html", animals=animals, preselected_animal_id=animal_id)


@staff_bp.route("/medical-records/<int:record_id>/edit", methods=["GET", "POST"])
@login_required
def medical_record_edit(record_id):
    db = get_db()
    cursor = db.cursor()

    cursor.execute(
        "SELECT record_id, animal_id, visit_date, outcome FROM Medical_Record WHERE record_id = %(record_id)s",
        {"record_id": record_id},
    )
    record = cursor.fetchone()
    if not record:
        flash("Medical record not found.", "error")
        return redirect(url_for("staff.medical_record_list"))

    cursor.execute("SELECT animal_id, name FROM Animal ORDER BY name")
    animals = cursor.fetchall()

    if request.method == "POST":
        animal_id = request.form.get("animal_id")
        visit_date = request.form.get("visit_date")
        outcome = request.form.get("outcome", "").strip()

        if not all([animal_id, visit_date]):
            flash("Animal and visit date are required.", "error")
            return render_template("staff_medical_record_edit_form.html", record=record, animals=animals)

        field_changes = {}
        new_animal_id = int(animal_id)
        if new_animal_id != record["animal_id"]:
            field_changes["animal_id"] = new_animal_id
        if visit_date != str(record["visit_date"]):
            field_changes["visit_date"] = visit_date
        new_outcome = outcome or None
        if new_outcome != (record["outcome"] or None):
            field_changes["outcome"] = new_outcome

        if not field_changes:
            flash("No changes detected.", "info")
            return redirect(url_for("staff.medical_record_list"))

        if session.get("staff_role") == "admin":
            apply_medical_record_edit("update", record_id, field_changes)
            db.commit()
            flash("Medical record updated.", "success")
            return redirect(url_for("staff.medical_record_list"))

        cursor.execute(
            """
            INSERT INTO Edit_Request (table_name, record_type, request_id, field_changes, status)
            VALUES (%(table_name)s, %(record_type)s, %(request_id)s, %(field_changes)s, 'pending')
            """,
            {
                "table_name": "Medical_Record",
                "record_type": "update",
                "request_id": record_id,
                "field_changes": json.dumps(field_changes),
            },
        )
        db.commit()
        flash("Medical record edit request submitted for admin approval.", "success")
        return redirect(url_for("staff.medical_record_list"))

    return render_template("staff_medical_record_edit_form.html", record=record, animals=animals)


@staff_bp.route("/medical-records/<int:record_id>/treatments")
@login_required
def medical_record_treatments(record_id):
    db = get_db()
    cursor = db.cursor()

    cursor.execute(
        """
        SELECT mr.record_id, mr.visit_date, mr.outcome, a.name as animal_name
        FROM Medical_Record mr
        JOIN Animal a ON mr.animal_id = a.animal_id
        WHERE mr.record_id = %(record_id)s
        """,
        {"record_id": record_id},
    )
    record = cursor.fetchone()

    if not record:
        flash("Medical record not found.", "error")
        return redirect(url_for("staff.medical_record_list"))

    cursor.execute(
        """
        SELECT t.treatment_id, t.treatment_type, t.medication, t.description, t.cost,
               v.first_name as vet_first, v.last_name as vet_last
        FROM Treatment t
        JOIN Vet v ON t.vet_id = v.vet_id
        WHERE t.record_id = %(record_id)s
        ORDER BY t.treatment_id
        """,
        {"record_id": record_id},
    )
    treatments = cursor.fetchall()

    return render_template("staff_treatments.html", record=record, treatments=treatments)


@staff_bp.route("/medical-records/<int:record_id>/treatments/propose", methods=["GET", "POST"])
@login_required
def propose_treatment(record_id):
    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT record_id FROM Medical_Record WHERE record_id = %(record_id)s", {"record_id": record_id})
    if not cursor.fetchone():
        flash("Medical record not found.", "error")
        return redirect(url_for("staff.medical_record_list"))

    cursor.execute("SELECT vet_id, first_name, last_name FROM Vet ORDER BY last_name")
    vets = cursor.fetchall()

    if request.method == "POST":
        vet_id = request.form.get("vet_id")
        treatment_type = request.form.get("treatment_type")

        if treatment_type == "Other":
            treatment_type_other = request.form.get("treatment_type_other", "").strip()
            if treatment_type_other:
                treatment_type = treatment_type_other

        medication = request.form.get("medication", "").strip()
        description = request.form.get("description", "").strip()
        cost = request.form.get("cost", "0")

        if not vet_id or not treatment_type:
            flash("Vet and treatment type are required.", "error")
            return render_template("staff_propose_treatment.html", record_id=record_id, vets=vets)

        try:
            cost_float = float(cost) if cost else 0.00
        except ValueError:
            flash("Cost must be a valid number.", "error")
            return render_template("staff_propose_treatment.html", record_id=record_id, vets=vets)

        if cost_float < 0:
            flash("Cost cannot be negative.", "error")
            return render_template("staff_propose_treatment.html", record_id=record_id, vets=vets)

        field_changes = {
            "record_id": record_id,
            "vet_id": int(vet_id),
            "treatment_type": treatment_type,
            "medication": medication or None,
            "description": description or None,
            "cost": cost_float,
        }

        if session.get("staff_role") == "admin":
            new_id = apply_treatment_edit("create", None, field_changes)
            db.commit()
            flash(f"Treatment created (ID: {new_id}).", "success")
            next_url = request.args.get('next')
            if next_url:
                return redirect(next_url)
            return redirect(url_for("staff.medical_record_treatments", record_id=record_id))

        cursor.execute(
            """
            INSERT INTO Edit_Request (table_name, record_type, field_changes, status)
            VALUES (%(table_name)s, %(record_type)s, %(field_changes)s, 'pending')
            """,
            {
                "table_name": "Treatment",
                "record_type": "create",
                "field_changes": json.dumps(field_changes),
            },
        )
        db.commit()

        flash("Treatment proposal submitted for admin approval.", "success")
        next_url = request.args.get('next')
        if next_url:
            return redirect(next_url)
        return redirect(url_for("staff.medical_record_treatments", record_id=record_id))

    return render_template("staff_propose_treatment.html", record_id=record_id, vets=vets)


@staff_bp.route("/medical-records/<int:record_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_medical_record(record_id):
    db = get_db()
    cursor = db.cursor()

    cursor.execute(
        "DELETE FROM Treatment WHERE record_id = %(record_id)s",
        {"record_id": record_id},
    )

    cursor.execute(
        "DELETE FROM Medical_Record WHERE record_id = %(record_id)s",
        {"record_id": record_id},
    )

    db.commit()
    flash("Medical record deleted.", "error")
    return redirect(url_for("staff.medical_record_list"))


@staff_bp.route("/treatments/<int:treatment_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_treatment(treatment_id):
    db = get_db()
    cursor = db.cursor()

    cursor.execute(
        "SELECT record_id FROM Treatment WHERE treatment_id = %(treatment_id)s",
        {"treatment_id": treatment_id},
    )
    row = cursor.fetchone()

    if not row:
        flash("Treatment not found.", "error")
        return redirect(url_for("staff.medical_record_list"))

    record_id = row["record_id"]

    cursor.execute(
        "DELETE FROM Treatment WHERE treatment_id = %(treatment_id)s",
        {"treatment_id": treatment_id},
    )
    db.commit()

    flash("Treatment deleted.", "error")
    return redirect(url_for("staff.medical_record_treatments", record_id=record_id))

@staff_bp.route("/treatments/<int:treatment_id>/edit", methods=["GET", "POST"])
@login_required
def edit_treatment(treatment_id):
    db = get_db()
    cursor = db.cursor()

    cursor.execute(
        """
        SELECT t.treatment_id, t.record_id, t.vet_id, t.treatment_type, t.medication, t.description, t.cost
        FROM Treatment t
        WHERE t.treatment_id = %(treatment_id)s
        """,
        {"treatment_id": treatment_id},
    )
    treatment = cursor.fetchone()

    if not treatment:
        flash("Treatment not found.", "error")
        return redirect(url_for("staff.medical_record_list"))

    cursor.execute("SELECT vet_id, first_name, last_name FROM Vet ORDER BY last_name")
    vets = cursor.fetchall()

    if request.method == "POST":
        vet_id = request.form.get("vet_id")
        treatment_type = request.form.get("treatment_type")

        if treatment_type == "Other":
            treatment_type_other = request.form.get("treatment_type_other", "").strip()
            if treatment_type_other:
                treatment_type = treatment_type_other

        medication = request.form.get("medication", "").strip()
        description = request.form.get("description", "").strip()
        cost = request.form.get("cost", "0")

        if not vet_id or not treatment_type:
            flash("Vet and treatment type are required.", "error")
            return render_template("staff_treatment_edit_form.html", treatment=treatment, vets=vets, record_id=treatment["record_id"])

        try:
            cost_float = float(cost) if cost else 0.00
        except ValueError:
            flash("Cost must be a valid number.", "error")
            return render_template("staff_treatment_edit_form.html", treatment=treatment, vets=vets, record_id=treatment["record_id"])

        if cost_float < 0:
            flash("Cost cannot be negative.", "error")
            return render_template("staff_treatment_edit_form.html", treatment=treatment, vets=vets, record_id=treatment["record_id"])

        field_changes = {
            "vet_id": int(vet_id),
            "treatment_type": treatment_type,
            "medication": medication or None,
            "description": description or None,
            "cost": cost_float,
        }

        if session.get("staff_role") == "admin":
            apply_treatment_edit("update", treatment_id, field_changes)
            db.commit()
            flash("Treatment updated.", "success")
            return redirect(url_for("staff.medical_record_treatments", record_id=treatment["record_id"]))
        else:
            cursor.execute(
                """
                INSERT INTO Edit_Request (table_name, record_type, request_id, field_changes, status)
                VALUES (%(table_name)s, %(record_type)s, %(request_id)s, %(field_changes)s, 'pending')
                """,
                {
                    "table_name": "Treatment",
                    "record_type": "update",
                    "request_id": treatment_id,
                    "field_changes": json.dumps(field_changes),
                },
            )
            db.commit()
            flash("Treatment edit request submitted for admin approval.", "success")
            return redirect(url_for("staff.medical_record_treatments", record_id=treatment["record_id"]))

    return render_template("staff_treatment_edit_form.html", treatment=treatment, vets=vets, record_id=treatment["record_id"])