import json
import os

import bcrypt
import click
from app.db import get_db


def init_app(app):
    """
    Registers our CLI commands onto the Flask app.
    Called once from create_app() so `flask --app run.py init-db` works.
    """
    app.cli.add_command(init_db_command)
    app.cli.add_command(seed_demo_command)


def _schema_path():
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), "schema.sql")


def _hash_password(password):
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


@click.command("init-db")
def init_db_command():
    """
    Creates all tables from schema.sql.

    Does NOT drop existing tables first — if a table already exists,
    MySQL will raise an error and this command will fail loudly rather
    than silently wiping data. That's intentional: re-running this by
    accident should never delete anything.
    """
    db = get_db()
    cursor = db.cursor()

    schema_file = os.path.normpath(_schema_path())
    with open(schema_file, "r") as f:
        sql_script = f.read()

    statements = [s.strip() for s in sql_script.split(";") if s.strip()]

    for statement in statements:
        cursor.execute(statement)

    db.commit()
    click.echo(f"Database initialized — {len(statements)} tables created.")


@click.command("seed-demo")
@click.option("--force", is_flag=True, help="Re-seed even if demo accounts already exist.")
def seed_demo_command(force):
    """
    Loads sample animals, applications, and staff accounts for demos.

    Creates demo_admin and demo_staff with known passwords (printed on success).
    Safe to run once; skips if demo_admin already exists unless --force is passed.
    """
    db = get_db()
    cursor = db.cursor()

    cursor.execute("SELECT staff_id FROM Staff WHERE username = %(username)s", {"username": "demo_admin"})
    if cursor.fetchone() and not force:
        click.echo("Demo data already exists (demo_admin found). Use --force to re-seed.")
        return

    if force:
        click.echo("Clearing existing demo rows...")
        cursor.execute("DELETE FROM Edit_Request")
        cursor.execute("DELETE FROM Treatment")
        cursor.execute("DELETE FROM Medical_Record")
        cursor.execute("DELETE FROM Adoption")
        cursor.execute("DELETE FROM Foster")
        cursor.execute("DELETE FROM Rescue")
        cursor.execute("DELETE FROM Donation_Info")
        cursor.execute("DELETE FROM Person_Contact")
        cursor.execute("DELETE FROM Person")
        cursor.execute("DELETE FROM Vet_Contact")
        cursor.execute("DELETE FROM Vet")
        cursor.execute("DELETE FROM Animal")
        cursor.execute("DELETE FROM Staff WHERE username IN ('demo_admin', 'demo_staff')")

    admin_password = "DemoAdmin1!"
    staff_password = "DemoStaff1!"

    cursor.execute(
        """
        INSERT INTO Staff (username, first_name, last_name, role, status, password)
        VALUES (%(username)s, %(first_name)s, %(last_name)s, 'admin', TRUE, %(password)s)
        """,
        {
            "username": "demo_admin",
            "first_name": "Demo",
            "last_name": "Admin",
            "password": _hash_password(admin_password),
        },
    )
    admin_id = cursor.lastrowid

    cursor.execute(
        """
        INSERT INTO Staff (username, first_name, last_name, role, status, password)
        VALUES (%(username)s, %(first_name)s, %(last_name)s, 'staff', TRUE, %(password)s)
        """,
        {
            "username": "demo_staff",
            "first_name": "Demo",
            "last_name": "Staff",
            "password": _hash_password(staff_password),
        },
    )

    animals = [
        ("Browny", "Dog", "Golden Retriever", "Male", "2022-03-15", "available", "Energetic and friendly."),
        ("Whiskers", "Cat", "Domestic Shorthair", "Female", "2021-08-02", "available", "Calm indoor cat."),
        ("Charlie", "Dog", "Beagle", "Male", "2020-11-20", "available", "Great with families."),
        ("Luna", "Cat", "Tabby", "Female", "2019-05-10", "fostered", "Currently in foster care."),
    ]
    animal_ids = {}
    for name, species, breed, sex, birth_date, status, notes in animals:
        cursor.execute(
            """
            INSERT INTO Animal (name, species, breed, sex, birth_date, status, notes)
            VALUES (%(name)s, %(species)s, %(breed)s, %(sex)s, %(birth_date)s, %(status)s, %(notes)s)
            """,
            {
                "name": name,
                "species": species,
                "breed": breed,
                "sex": sex,
                "birth_date": birth_date,
                "status": status,
                "notes": notes,
            },
        )
        animal_ids[name] = cursor.lastrowid

    cursor.execute(
        "INSERT INTO Person (first_name, last_name) VALUES ('Jane', 'Doe')"
    )
    jane_id = cursor.lastrowid
    cursor.execute(
        """
        INSERT INTO Person_Contact (person_id, contact_type, contact_value)
        VALUES (%(person_id)s, 'email', 'jane.doe@example.com')
        """,
        {"person_id": jane_id},
    )
    cursor.execute(
        """
        INSERT INTO Person_Contact (person_id, contact_type, contact_value)
        VALUES (%(person_id)s, 'phone', '+15551234567')
        """,
        {"person_id": jane_id},
    )

    cursor.execute(
        "INSERT INTO Person (first_name, last_name) VALUES ('John', 'Smith')"
    )
    john_id = cursor.lastrowid
    cursor.execute(
        """
        INSERT INTO Person_Contact (person_id, contact_type, contact_value)
        VALUES (%(person_id)s, 'email', 'john.smith@example.com')
        """,
        {"person_id": john_id},
    )

    cursor.execute(
        "INSERT INTO Person (first_name, last_name) VALUES ('Maria', 'Garcia')"
    )
    maria_id = cursor.lastrowid
    cursor.execute(
        """
        INSERT INTO Person_Contact (person_id, contact_type, contact_value)
        VALUES (%(person_id)s, 'email', 'maria.garcia@example.com')
        """,
        {"person_id": maria_id},
    )

    cursor.execute(
        """
        INSERT INTO Adoption (person_id, animal_id, status)
        VALUES (%(person_id)s, %(animal_id)s, 'pending')
        """,
        {"person_id": jane_id, "animal_id": animal_ids["Charlie"]},
    )

    cursor.execute(
        """
        INSERT INTO Foster (person_id, animal_id, notes, status)
        VALUES (%(person_id)s, %(animal_id)s, 'Has a quiet home with a fenced yard.', 'pending')
        """,
        {"person_id": maria_id, "animal_id": animal_ids["Whiskers"]},
    )

    cursor.execute(
        """
        INSERT INTO Rescue (person_id, rescue_date, location, notes, animal_species, status)
        VALUES (%(person_id)s, CURDATE(), 'Central Park near 5th Ave', 'Found alone, seems healthy.', 'Dog', 'pending')
        """,
        {"person_id": john_id},
    )

    cursor.execute(
        """
        INSERT INTO Edit_Request (table_name, record_type, request_id, field_changes, status)
        VALUES ('Animal', 'update', %(request_id)s, %(field_changes)s, 'pending')
        """,
        {
            "request_id": animal_ids["Browny"],
            "field_changes": json.dumps({
                "notes": "Friendly with kids. Loves walks and fetch.",
            }),
        },
    )

    cursor.execute(
        """
        INSERT INTO Vet (first_name, last_name, affiliation)
        VALUES ('Amy', 'Chen', 'City Animal Clinic')
        """
    )
    vet_id = cursor.lastrowid
    cursor.execute(
        """
        INSERT INTO Vet_Contact (vet_id, contact_type, contact_value)
        VALUES (%(vet_id)s, 'phone', '+15559876543')
        """,
        {"vet_id": vet_id},
    )

    cursor.execute(
        """
        INSERT INTO Medical_Record (animal_id, visit_date, outcome)
        VALUES (%(animal_id)s, '2025-01-10', 'Routine checkup — healthy')
        """,
        {"animal_id": animal_ids["Charlie"]},
    )

    donation_items = [
        ("PayPal", "donate@animalshelter.example.org", False, 1),
        ("Venmo", "@AnimalShelterDemo", False, 2),
        ("Wish List", "https://example.org/wishlist", False, 3),
    ]
    for label, content, is_image, display_order in donation_items:
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
                "updated_by": admin_id,
            },
        )

    db.commit()

    click.echo("Demo data seeded successfully.")
    click.echo("")
    click.echo("Staff accounts:")
    click.echo("  Admin  - username: demo_admin   password: DemoAdmin1!")
    click.echo("  Staff  - username: demo_staff   password: DemoStaff1!")
    click.echo("")
    click.echo("Sample data:")
    click.echo("  4 animals (Browny, Whiskers, Charlie, Luna)")
    click.echo("  1 pending adoption (Jane -> Charlie)")
    click.echo("  1 pending foster (Maria -> Whiskers)")
    click.echo("  1 pending rescue report (John Smith)")
    click.echo("  1 pending edit ticket (Browny notes update)")
    click.echo("  1 vet, 1 medical record, donation info")
