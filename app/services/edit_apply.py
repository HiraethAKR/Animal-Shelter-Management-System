"""
Turns an approved Edit_Request row into a real INSERT or UPDATE.

Why one function per entity instead of one generic handler:
- Security: building table/column names from arbitrary strings (even after
  validating table_name against an allowlist) is fragile and easy to get
  wrong. Writing the SQL explicitly for each table means there's no
  string-built identifier anywhere in this file.
- Debuggability: if something goes wrong applying an Animal edit, you can
  set a breakpoint in apply_animal_edit() and see exactly what ran. A
  generic reflection-based handler hides that behind indirection.

Each apply_*_edit() function:
  1. Takes the parsed field_changes dict, the record_type, and (for
     updates) the target record_id.
  2. Runs ONE explicit INSERT or UPDATE against its one specific table.
  3. Returns the new/updated row's primary key on success.

These functions do NOT commit the transaction and do NOT update the
Edit_Request row's own status — that's the caller's job (the route that
handles the "approve" button), so one failed step doesn't leave things
half-applied. See the approval route once we build it.
"""

from app.db import get_db


def apply_animal_edit(record_type, record_id, field_changes):
    """
    Applies an approved Animal edit.

    field_changes is a dict already parsed from JSON, e.g.:
      {"name": "Browny", "species": "Dog", "sex": "Male", "status": "available"}

    record_type='create' -> INSERT a new Animal row, return its new animal_id
    record_type='update' -> UPDATE the existing Animal row at record_id
    """
    db = get_db()
    cursor = db.cursor()

    if record_type == "create":
        cursor.execute(
            """
            INSERT INTO Animal (name, species, breed, sex, birth_date, status, notes, image_url)
            VALUES (%(name)s, %(species)s, %(breed)s, %(sex)s, %(birth_date)s, %(status)s, %(notes)s, %(image_url)s)
            """,
            {
                "name": field_changes.get("name"),
                "species": field_changes.get("species"),
                "breed": field_changes.get("breed"),
                "sex": field_changes.get("sex"),
                "birth_date": field_changes.get("birth_date"),
                "status": field_changes.get("status"),
                "notes": field_changes.get("notes"),
                "image_url": field_changes.get("image_url"),
            },
        )
        return cursor.lastrowid

    elif record_type == "update":
        set_clauses = []
        params = {"animal_id": record_id}
        for field in ("name", "species", "breed", "sex", "birth_date", "status", "notes", "image_url"):
            if field in field_changes:
                set_clauses.append(f"{field} = %({field})s")
                params[field] = field_changes[field]

        if not set_clauses:
            return record_id  # nothing to change

        sql = f"UPDATE Animal SET {', '.join(set_clauses)} WHERE animal_id = %(animal_id)s"
        cursor.execute(sql, params)
        if cursor.rowcount == 0:
            raise RuntimeError(f"Animal ID {record_id} no longer exists")
        return record_id

    else:
        raise ValueError(f"Unknown record_type: {record_type}")


def apply_vet_edit(record_type, record_id, field_changes):
    db = get_db()
    cursor = db.cursor()

    if record_type == "create":
        cursor.execute(
            """
            INSERT INTO Vet (first_name, last_name, affiliation)
            VALUES (%(first_name)s, %(last_name)s, %(affiliation)s)
            """,
            {
                "first_name": field_changes.get("first_name"),
                "last_name": field_changes.get("last_name"),
                "affiliation": field_changes.get("affiliation"),
            },
        )
        vet_id = cursor.lastrowid

        for contact in field_changes.get("contacts", []):
            cursor.execute(
                """
                INSERT INTO Vet_Contact (vet_id, contact_type, contact_value)
                VALUES (%(vet_id)s, %(contact_type)s, %(contact_value)s)
                """,
                {
                    "vet_id": vet_id,
                    "contact_type": contact.get("contact_type"),
                    "contact_value": contact.get("contact_value"),
                },
            )
        return vet_id

    elif record_type == "update":
        set_clauses = []
        params = {"vet_id": record_id}
        for field in ("first_name", "last_name", "affiliation"):
            if field in field_changes:
                set_clauses.append(f"{field} = %({field})s")
                params[field] = field_changes[field]

        if set_clauses:
            sql = f"UPDATE Vet SET {', '.join(set_clauses)} WHERE vet_id = %(vet_id)s"
            cursor.execute(sql, params)
            if cursor.rowcount == 0:
                raise RuntimeError(f"Vet ID {record_id} no longer exists")

        if "contacts" in field_changes:
            cursor.execute("DELETE FROM Vet_Contact WHERE vet_id = %(vet_id)s", {"vet_id": record_id})
            for contact in field_changes["contacts"]:
                cursor.execute(
                    """
                    INSERT INTO Vet_Contact (vet_id, contact_type, contact_value)
                    VALUES (%(vet_id)s, %(contact_type)s, %(contact_value)s)
                    """,
                    {
                        "vet_id": record_id,
                        "contact_type": contact.get("contact_type"),
                        "contact_value": contact.get("contact_value"),
                    },
                )

        return record_id

    else:
        raise ValueError(f"Unknown record_type: {record_type}")


def apply_medical_record_edit(record_type, record_id, field_changes):
    """
    Turns an approved Edit_Request into a real INSERT or UPDATE on Medical_Record.
    """
    db = get_db()
    cursor = db.cursor()

    if record_type == "create":
        cursor.execute(
            """
            INSERT INTO Medical_Record (animal_id, visit_date, outcome)
            VALUES (%(animal_id)s, %(visit_date)s, %(outcome)s)
            """,
            {
                "animal_id": field_changes.get("animal_id"),
                "visit_date": field_changes.get("visit_date"),
                "outcome": field_changes.get("outcome"),
            },
        )
        return cursor.lastrowid

    elif record_type == "update":
        set_clauses = []
        params = {"record_id": record_id}

        for field in ("animal_id", "visit_date", "outcome"):
            if field in field_changes:
                set_clauses.append(f"{field} = %({field})s")
                params[field] = field_changes[field]

        if not set_clauses:
            return record_id

        sql = f"UPDATE Medical_Record SET {', '.join(set_clauses)} WHERE record_id = %(record_id)s"
        cursor.execute(sql, params)
        if cursor.rowcount == 0:
            raise RuntimeError(f"Medical Record ID {record_id} no longer exists")
        return record_id

    else:
        raise ValueError(f"Unknown record_type: {record_type}")


def apply_treatment_edit(record_type, record_id, field_changes):
    """
    Turns an approved Edit_Request into a real INSERT or UPDATE on Treatment.
    """
    db = get_db()
    cursor = db.cursor()

    if record_type == "create":
        cursor.execute(
            """
            INSERT INTO Treatment (record_id, vet_id, treatment_type, medication, description, cost)
            VALUES (%(record_id)s, %(vet_id)s, %(treatment_type)s, %(medication)s, %(description)s, %(cost)s)
            """,
            {
                "record_id": field_changes.get("record_id"),
                "vet_id": field_changes.get("vet_id"),
                "treatment_type": field_changes.get("treatment_type"),
                "medication": field_changes.get("medication"),
                "description": field_changes.get("description"),
                "cost": field_changes.get("cost"),
            },
        )
        return cursor.lastrowid

    elif record_type == "update":
        set_clauses = []
        params = {"treatment_id": record_id}

        for field in ("record_id", "vet_id", "treatment_type", "medication", "description", "cost"):
            if field in field_changes:
                set_clauses.append(f"{field} = %({field})s")
                params[field] = field_changes[field]

        if not set_clauses:
            return record_id

        sql = f"UPDATE Treatment SET {', '.join(set_clauses)} WHERE treatment_id = %(treatment_id)s"
        cursor.execute(sql, params)
        if cursor.rowcount == 0:
            raise RuntimeError(f"Treatment ID {record_id} no longer exists")
        return record_id

    else:
        raise ValueError(f"Unknown record_type: {record_type}")


# ---------------------------------------------------------------------------
# Edit_Request dispatch table
# ---------------------------------------------------------------------------
EDIT_HANDLERS = {
    "Animal": {
        "create": apply_animal_edit,
        "update": apply_animal_edit,
    },
    "Vet": {
        "create": apply_vet_edit,
        "update": apply_vet_edit,
    },
    "Medical_Record": {
        "create": apply_medical_record_edit,
        "update": apply_medical_record_edit,
    },
    "Treatment": {
        "create": apply_treatment_edit,
        "update": apply_treatment_edit,
    },
}