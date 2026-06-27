import json
import datetime
import os
import re
import uuid
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from werkzeug.utils import secure_filename
from app.db import get_db
from app.services.edit_apply import apply_animal_edit

public_bp = Blueprint("public", __name__)

PHONE_REGEX = re.compile(r'^[\d\+\-]{9,16}$')
EMAIL_REGEX = re.compile(r'^[^@]+@[^@]+\.[^@]+$')
ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


def _calculate_age(birth_date):
    """
    Calculate a human-readable age string from a date or ISO date string.
    Returns None if birth_date is missing.
    """
    if not birth_date:
        return None
    today = datetime.date.today()
    if isinstance(birth_date, str):
        try:
            birth_date = datetime.date.fromisoformat(birth_date)
        except ValueError:
            return None
    if birth_date > today:
        return None
    years = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
    if years >= 1:
        return f"{years} year{'s' if years != 1 else ''}"
    months = (today.year - birth_date.year) * 12 + today.month - birth_date.month
    if today.day < birth_date.day:
        months -= 1
    if months >= 1:
        return f"{months} month{'s' if months != 1 else ''}"
    days = (today - birth_date).days
    weeks = days // 7
    if weeks >= 1:
        return f"{weeks} week{'s' if weeks != 1 else ''}"
    return f"{days} day{'s' if days != 1 else ''}"


@public_bp.route("/")
def index():
    return redirect(url_for("public.animal_list"))


def _validate_contacts(contact_types, contact_values):
    errors = []
    for ct, cv in zip(contact_types, contact_values):
        cv = cv.strip()
        if not cv:
            continue
        if ct == "phone" and not PHONE_REGEX.match(cv):
            errors.append(f"Invalid phone number: {cv} (use 9-16 digits, + and - only)")
        elif ct == "email" and not EMAIL_REGEX.match(cv):
            errors.append(f"Invalid email: {cv}")
    return errors


def _get_or_create_person(contact_types, contact_values, first_name, last_name):
    db = get_db()
    cursor = db.cursor()

    contacts = []
    for ct, cv in zip(contact_types, contact_values):
        cv = cv.strip()
        if ct and cv:
            contacts.append((ct, cv))

    if not contacts:
        return None

    for _, cv in contacts:
        cursor.execute(
            "SELECT person_id FROM Person_Contact WHERE contact_value = %(contact_value)s",
            {"contact_value": cv},
        )
        row = cursor.fetchone()
        if row:
            person_id = row["person_id"]
            for ct, cv2 in contacts:
                cursor.execute(
                    "SELECT contact_id FROM Person_Contact WHERE contact_value = %(contact_value)s",
                    {"contact_value": cv2},
                )
                if not cursor.fetchone():
                    cursor.execute(
                        """
                        INSERT INTO Person_Contact (person_id, contact_type, contact_value)
                        VALUES (%(person_id)s, %(contact_type)s, %(contact_value)s)
                        """,
                        {"person_id": person_id, "contact_type": ct, "contact_value": cv2},
                    )
            return person_id

    cursor.execute(
        "INSERT INTO Person (first_name, last_name) VALUES (%(first_name)s, %(last_name)s)",
        {"first_name": first_name, "last_name": last_name},
    )
    person_id = cursor.lastrowid

    for ct, cv in contacts:
        cursor.execute(
            """
            INSERT INTO Person_Contact (person_id, contact_type, contact_value)
            VALUES (%(person_id)s, %(contact_type)s, %(contact_value)s)
            """,
            {"person_id": person_id, "contact_type": ct, "contact_value": cv},
        )

    return person_id


def _save_animal_image(image_file):
    if not image_file or not image_file.filename:
        return None
    filename = secure_filename(image_file.filename)
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValueError(f"Invalid file type '{ext}'. Allowed: {', '.join(ALLOWED_IMAGE_EXTENSIONS)}")
    unique_name = f"{uuid.uuid4().hex}_{filename}"
    upload_dir = os.path.join(current_app.root_path, "static", "uploads", "animals")
    os.makedirs(upload_dir, exist_ok=True)
    image_file.save(os.path.join(upload_dir, unique_name))
    return f"uploads/animals/{unique_name}"


def _save_rescue_photo(image_file):
    if not image_file or not image_file.filename:
        return None
    filename = secure_filename(image_file.filename)
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValueError(f"Invalid file type '{ext}'. Allowed: {', '.join(ALLOWED_IMAGE_EXTENSIONS)}")
    unique_name = f"{uuid.uuid4().hex}_{filename}"
    upload_dir = os.path.join(current_app.root_path, "static", "uploads", "rescues")
    os.makedirs(upload_dir, exist_ok=True)
    image_file.save(os.path.join(upload_dir, unique_name))
    return f"uploads/rescues/{unique_name}"


@public_bp.route("/animals")
def animal_list():
    db = get_db()
    cursor = db.cursor()

    page = request.args.get("page", 1, type=int)
    per_page = 12
    offset = (page - 1) * per_page

    where_clauses = []
    params = {}

    q = request.args.get("q", "").strip()
    if q:
        where_clauses.append("(name LIKE %(q)s OR breed LIKE %(q)s)")
        params["q"] = f"%{q}%"

    species = request.args.get("species")
    species_other = request.args.get("species_other", "").strip()

    if species == "Other" and species_other:
        where_clauses.append("species = %(species)s")
        params["species"] = species_other
    elif species and species != "Other":
        where_clauses.append("species = %(species)s")
        params["species"] = species
    elif species == "Other" and not species_other:
        where_clauses.append("species NOT IN ('Dog', 'Cat', 'Bird', 'Rabbit')")

    status = request.args.get("status")
    if status:
        where_clauses.append("status = %(status)s")
        params["status"] = status

    sex = request.args.get("sex")
    if sex:
        where_clauses.append("sex = %(sex)s")
        params["sex"] = sex

    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

    if where_sql == "1=1":
        where_sql = "is_deleted = 0"
    else:
        where_sql = where_sql + " AND is_deleted = 0"
    cursor.execute(f"SELECT COUNT(*) as total FROM Animal WHERE {where_sql}", params)
    total = cursor.fetchone()["total"]
    pages = (total + per_page - 1) // per_page

    sort = request.args.get("sort", "name")
    if sort == "newest":
        order_by = "animal_id DESC"
    else:
        order_by = "name ASC"

    query = f"SELECT animal_id, name, species, breed, status, birth_date, image_url FROM Animal WHERE {where_sql} ORDER BY {order_by} LIMIT %(limit)s OFFSET %(offset)s"
    params["limit"] = per_page
    params["offset"] = offset

    cursor.execute(query, params)
    animals = cursor.fetchall()

    for a in animals:
        a["age"] = _calculate_age(a.get("birth_date"))

    return render_template(
        "animals.html",
        animals=animals,
        page=page,
        pages=pages,
        total=total,
        current_args=request.args
    )


@public_bp.route("/animals/new", methods=["GET", "POST"])
def animal_create():
    if not session.get("staff_id"):
        flash("Please log in as staff to request new animals.", "error")
        return redirect(url_for("staff.login"))

    form_data = {}

    if request.method == "POST":
        form_data = {
            "name": request.form.get("name", ""),
            "species": request.form.get("species", ""),
            "species_other": request.form.get("species_other", ""),
            "breed": request.form.get("breed", ""),
            "sex": request.form.get("sex", ""),
            "birth_date": request.form.get("birth_date", ""),
            "status": request.form.get("status", ""),
            "notes": request.form.get("notes", ""),
        }

        if form_data["species"] == "Other":
            species_other = form_data["species_other"].strip()
            if species_other:
                form_data["species"] = species_other

        if form_data["birth_date"]:
            try:
                birth = datetime.date.fromisoformat(form_data["birth_date"])
                if birth > datetime.date.today():
                    flash("Birth date cannot be in the future.", "error")
                    return render_template("animal_form.html", form_data=form_data)
            except ValueError:
                flash("Invalid birth date format.", "error")
                return render_template("animal_form.html", form_data=form_data)

        try:
            image_url = _save_animal_image(request.files.get("image"))
        except ValueError as e:
            flash(str(e), "error")
            return render_template("animal_form.html", form_data=form_data)

        field_changes = {
            "name": form_data["name"] or None,
            "species": form_data["species"] or None,
            "breed": form_data["breed"] or None,
            "sex": form_data["sex"] or None,
            "birth_date": form_data["birth_date"] or None,
            "status": form_data["status"] or None,
            "notes": form_data["notes"] or None,
            "image_url": image_url,
        }

        db = get_db()
        cursor = db.cursor()

        if session.get("staff_role") == "admin":
            new_id = apply_animal_edit("create", None, field_changes)
            db.commit()
            flash(f"Animal created (ID: {new_id}).", "success")
            return redirect(url_for("public.animal_list"))

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

        flash("Your request has been submitted for review.", "success")
        return redirect(url_for("public.animal_list"))

    return render_template("animal_form.html", form_data=form_data)


@public_bp.route("/animals/<int:animal_id>")
def animal_detail(animal_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        "SELECT animal_id, name, species, breed, sex, birth_date, status, notes, image_url FROM Animal WHERE animal_id = %(animal_id)s",
        {"animal_id": animal_id},
    )
    animal = cursor.fetchone()
    if not animal:
        flash("Animal not found.", "error")
        return redirect(url_for("public.animal_list"))

    animal["age"] = _calculate_age(animal["birth_date"])

    cursor.execute(
        """
        SELECT record_id, visit_date, outcome
        FROM Medical_Record
        WHERE animal_id = %(animal_id)s
        ORDER BY visit_date DESC
        """,
        {"animal_id": animal_id},
    )
    medical_records = cursor.fetchall()

    for record in medical_records:
        cursor.execute(
            """
            SELECT t.treatment_id, t.treatment_type, t.medication, t.description, t.cost,
                   v.first_name as vet_first, v.last_name as vet_last
            FROM Treatment t
            JOIN Vet v ON t.vet_id = v.vet_id
            WHERE t.record_id = %(record_id)s
            ORDER BY t.treatment_id
            """,
            {"record_id": record["record_id"]},
        )
        record["treatments"] = cursor.fetchall()

    return render_template("animal_detail.html", animal=animal, medical_records=medical_records)


@public_bp.route("/animals/<int:animal_id>/edit", methods=["GET", "POST"])
def animal_edit_request(animal_id):
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        "SELECT animal_id, name, species, breed, sex, birth_date, status, notes, image_url FROM Animal WHERE animal_id = %(animal_id)s",
        {"animal_id": animal_id},
    )
    animal = cursor.fetchone()
    if not animal:
        flash("Animal not found.", "error")
        return redirect(url_for("public.animal_list"))

    if not session.get("staff_id"):
        flash("Please log in as staff to propose edits.", "error")
        return redirect(url_for("staff.login"))

    if request.method == "POST":
        field_changes = {}
        for field in ("name", "species", "breed", "sex", "birth_date", "status", "notes"):
            value = request.form.get(field)
            if value and value != str(animal[field] or ""):
                field_changes[field] = value

        if field_changes.get("species") == "Other":
            species_other = request.form.get("species_other", "").strip()
            if species_other:
                field_changes["species"] = species_other

        try:
            image_url = _save_animal_image(request.files.get("image"))
        except ValueError as e:
            flash(str(e), "error")
            return render_template("animal_edit_form.html", animal=animal)

        if image_url:
            field_changes["image_url"] = image_url

        if not field_changes:
            flash("No changes detected.", "info")
            return redirect(url_for("public.animal_detail", animal_id=animal_id))

        if session.get("staff_role") == "admin":
            apply_animal_edit("update", animal_id, field_changes)
            db.commit()
            flash("Animal updated.", "success")
            return redirect(url_for("public.animal_detail", animal_id=animal_id))

        cursor.execute(
            """
            INSERT INTO Edit_Request (table_name, record_type, request_id, field_changes, status)
            VALUES (%(table_name)s, %(record_type)s, %(request_id)s, %(field_changes)s, 'pending')
            """,
            {
                "table_name": "Animal",
                "record_type": "update",
                "request_id": animal_id,
                "field_changes": json.dumps(field_changes),
            },
        )
        db.commit()

        flash("Your edit request has been submitted for review.", "success")
        return redirect(url_for("public.animal_detail", animal_id=animal_id))

    return render_template("animal_edit_form.html", animal=animal)


@public_bp.route("/rescue", methods=["GET", "POST"])
def rescue():
    form_data = {
        "animal_species": "",
        "location": "",
        "notes": "",
        "contacts": [],
    }

    if request.method == "POST":
        contact_types = request.form.getlist("contact_type[]")
        contact_values = request.form.getlist("contact_value[]")

        form_data = {
            "first_name": request.form.get("first_name", "").strip(),
            "last_name": request.form.get("last_name", "").strip(),
            "location": request.form.get("location", "").strip(),
            "notes": request.form.get("notes", ""),
            "animal_species": request.form.get("animal_species", ""),
            "contacts": [{"contact_type": ct, "contact_value": cv.strip()} for ct, cv in zip(contact_types, contact_values) if cv.strip()],
        }

        if form_data["animal_species"] == "Other":
            species_other = request.form.get("species_other", "").strip()
            if species_other:
                form_data["animal_species"] = species_other

        if not form_data["first_name"] or not form_data["last_name"]:
            flash("Name is required.", "error")
            return render_template("rescue_form.html", form_data=form_data)

        validation_errors = _validate_contacts(contact_types, contact_values)
        if validation_errors:
            for err in validation_errors:
                flash(err, "error")
            return render_template("rescue_form.html", form_data=form_data)

        if not request.files.get("photo") or not request.files.get("photo").filename:
            flash("A photo of the animal is required.", "error")
            return render_template("rescue_form.html", form_data=form_data)

        if not form_data["animal_species"]:
            flash("Species is required.", "error")
            return render_template("rescue_form.html", form_data=form_data)

        if not form_data["location"]:
            flash("Location is required.", "error")
            return render_template("rescue_form.html", form_data=form_data)

        try:
            photo_url = _save_rescue_photo(request.files.get("photo"))
        except ValueError as e:
            flash(str(e), "error")
            return render_template("rescue_form.html", form_data=form_data)

        person_id = _get_or_create_person(
            contact_types, contact_values,
            form_data["first_name"], form_data["last_name"]
        )

        if not person_id:
            flash("At least one contact is required.", "error")
            return render_template("rescue_form.html", form_data=form_data)

        db = get_db()
        cursor = db.cursor()
        cursor.execute(
            """
            INSERT INTO Rescue (person_id, animal_id, rescue_date, location, notes, animal_species, photo_url, status)
            VALUES (%(person_id)s, NULL, %(rescue_date)s, %(location)s, %(notes)s, %(animal_species)s, %(photo_url)s, 'pending')
            """,
            {
                "person_id": person_id,
                "rescue_date": datetime.date.today().isoformat(),
                "location": form_data["location"],
                "notes": form_data["notes"] or None,
                "animal_species": form_data["animal_species"],
                "photo_url": photo_url,
            },
        )
        db.commit()

        return redirect(url_for("public.success", msg="Your rescue report has been submitted for review.", title="Rescue Report Submitted"))

    return render_template("rescue_form.html", form_data=form_data)


@public_bp.route("/adopt", methods=["GET", "POST"])
def adopt():
    form_data = {}
    preselected_animal_id = request.args.get("animal_id", "")

    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        "SELECT animal_id, name, species, breed FROM Animal WHERE status = 'available' AND is_deleted = 0 ORDER BY name"
    )
    available_animals = cursor.fetchall()

    if request.method == "POST":
        contact_types = request.form.getlist("contact_type[]")
        contact_values = request.form.getlist("contact_value[]")

        form_data = {
            "first_name": request.form.get("first_name", "").strip(),
            "last_name": request.form.get("last_name", "").strip(),
            "animal_id": request.form.get("animal_id", ""),
            "notes": request.form.get("notes", ""),
            "contacts": [{"contact_type": ct, "contact_value": cv.strip()} for ct, cv in zip(contact_types, contact_values) if cv.strip()],
        }

        if not all([form_data["first_name"], form_data["last_name"], form_data["animal_id"]]):
            flash("All fields except notes are required.", "error")
            return render_template("adoption_form.html", form_data=form_data, animals=available_animals)

        validation_errors = _validate_contacts(contact_types, contact_values)
        if validation_errors:
            for err in validation_errors:
                flash(err, "error")
            return render_template("adoption_form.html", form_data=form_data, animals=available_animals)

        person_id = _get_or_create_person(
            contact_types, contact_values,
            form_data["first_name"], form_data["last_name"]
        )

        if not person_id:
            flash("At least one contact is required.", "error")
            return render_template("adoption_form.html", form_data=form_data, animals=available_animals)

        cursor.execute(
            "SELECT status FROM Animal WHERE animal_id = %(animal_id)s",
            {"animal_id": int(form_data["animal_id"])},
        )
        animal_row = cursor.fetchone()
        if not animal_row or animal_row["status"] != "available":
            flash("That animal is no longer available.", "error")
            return render_template("adoption_form.html", form_data=form_data, animals=available_animals)

        cursor.execute(
            """
            INSERT INTO Adoption (person_id, animal_id, status, submitted_at)
            VALUES (%(person_id)s, %(animal_id)s, 'pending', NOW())
            """,
            {"person_id": person_id, "animal_id": int(form_data["animal_id"])},
        )
        db.commit()

        return redirect(url_for("public.success", msg="Your adoption request has been submitted for review.", title="Adoption Application Submitted"))

    form_data["animal_id"] = preselected_animal_id
    return render_template("adoption_form.html", form_data=form_data, animals=available_animals)


@public_bp.route("/foster", methods=["GET", "POST"])
def foster():
    form_data = {}

    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        "SELECT animal_id, name, species, breed FROM Animal WHERE status = 'available' AND is_deleted = 0 ORDER BY name"
    )
    available_animals = cursor.fetchall()

    if request.method == "POST":
        contact_types = request.form.getlist("contact_type[]")
        contact_values = request.form.getlist("contact_value[]")

        form_data = {
            "first_name": request.form.get("first_name", "").strip(),
            "last_name": request.form.get("last_name", "").strip(),
            "animal_id": request.form.get("animal_id", ""),
            "start_date": request.form.get("start_date", ""),
            "end_date": request.form.get("end_date", ""),
            "notes": request.form.get("notes", ""),
            "contacts": [{"contact_type": ct, "contact_value": cv.strip()} for ct, cv in zip(contact_types, contact_values) if cv.strip()],
        }

        if not all([form_data["first_name"], form_data["last_name"],
                    form_data["animal_id"], form_data["start_date"]]):
            flash("All fields except end date and notes are required.", "error")
            return render_template("foster_form.html", form_data=form_data, animals=available_animals)

        if form_data["end_date"]:
            try:
                start = datetime.date.fromisoformat(form_data["start_date"])
                end = datetime.date.fromisoformat(form_data["end_date"])
                if end < start:
                    flash("End date cannot be before start date.", "error")
                    return render_template("foster_form.html", form_data=form_data, animals=available_animals)
            except ValueError:
                flash("Invalid date format.", "error")
                return render_template("foster_form.html", form_data=form_data, animals=available_animals)

        validation_errors = _validate_contacts(contact_types, contact_values)
        if validation_errors:
            for err in validation_errors:
                flash(err, "error")
            return render_template("foster_form.html", form_data=form_data, animals=available_animals)

        person_id = _get_or_create_person(
            contact_types, contact_values,
            form_data["first_name"], form_data["last_name"]
        )

        if not person_id:
            flash("At least one contact is required.", "error")
            return render_template("foster_form.html", form_data=form_data, animals=available_animals)

        cursor.execute(
            "SELECT status FROM Animal WHERE animal_id = %(animal_id)s",
            {"animal_id": int(form_data["animal_id"])},
        )
        animal_row = cursor.fetchone()
        if not animal_row or animal_row["status"] != "available":
            flash("That animal is no longer available.", "error")
            return render_template("foster_form.html", form_data=form_data, animals=available_animals)

        cursor.execute(
            """
            INSERT INTO Foster (person_id, animal_id, start_date, end_date, notes, status)
            VALUES (%(person_id)s, %(animal_id)s, %(start_date)s, %(end_date)s, %(notes)s, 'pending')
            """,
            {
                "person_id": person_id,
                "animal_id": int(form_data["animal_id"]),
                "start_date": form_data["start_date"],
                "end_date": form_data["end_date"] or None,
                "notes": form_data["notes"] or None,
            },
        )
        db.commit()

        return redirect(url_for("public.success", msg="Your foster request has been submitted for review.", title="Foster Application Submitted"))

    return render_template("foster_form.html", form_data=form_data, animals=available_animals)


@public_bp.route("/success")
def success():
    msg = request.args.get("msg", "Your submission has been received.")
    title = request.args.get("title", "Thank You!")
    return render_template("success.html", msg=msg, title=title)


@public_bp.route("/donate")
def donate():
    db = get_db()
    cursor = db.cursor()
    cursor.execute(
        """
        SELECT label, content, is_image
        FROM Donation_Info
        WHERE is_active = TRUE
        ORDER BY display_order ASC, info_id ASC
        """
    )
    channels = cursor.fetchall()
    return render_template("donate.html", channels=channels)
