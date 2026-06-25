from flask import Blueprint, render_template, session, redirect, url_for
from app.db import get_db

logbook_bp = Blueprint("logbook", __name__)


def _staff_required():
    if "staff_id" not in session:
        return redirect(url_for("staff.login"))


@logbook_bp.route("/staff/logbook")
def logbook():
    redir = _staff_required()
    if redir:
        return redir

    db = get_db()
    cursor = db.cursor()

    cursor.execute(
        """
        SELECT
            ad.adoption_id,
            ad.adoption_date,
            ad.submitted_at,
            CONCAT(p.first_name, ' ', p.last_name)  AS adopter_name,
            COALESCE(
                (SELECT pc.contact_value FROM Person_Contact pc
                 WHERE pc.person_id = p.person_id AND pc.contact_type = 'email' LIMIT 1),
                (SELECT pc.contact_value FROM Person_Contact pc
                 WHERE pc.person_id = p.person_id AND pc.contact_type = 'phone' LIMIT 1)
            )                                          AS adopter_contact,
            a.animal_id,
            a.name                                     AS animal_name,
            a.species,
            a.breed,
            COALESCE(a.is_deleted, 0)                  AS animal_deleted,
            CONCAT(s.first_name, ' ', s.last_name)   AS reviewed_by_name
        FROM   Adoption ad
        JOIN   Person   p  ON ad.person_id  = p.person_id
        JOIN   Animal   a  ON ad.animal_id  = a.animal_id
        LEFT JOIN Staff s  ON ad.reviewed_by = s.staff_id
        WHERE  ad.status = 'approved'
        ORDER  BY ad.adoption_date DESC, ad.submitted_at DESC
        """
    )
    adoptions = cursor.fetchall()

    cursor.execute(
        """
        SELECT
            f.foster_id,
            f.start_date,
            f.end_date,
            f.submitted_at,
            f.notes,
            CONCAT(p.first_name, ' ', p.last_name)   AS foster_name,
            COALESCE(
                (SELECT pc.contact_value FROM Person_Contact pc
                 WHERE pc.person_id = p.person_id AND pc.contact_type = 'email' LIMIT 1),
                (SELECT pc.contact_value FROM Person_Contact pc
                 WHERE pc.person_id = p.person_id AND pc.contact_type = 'phone' LIMIT 1)
            )                                           AS foster_contact,
            a.animal_id,
            a.name                                      AS animal_name,
            a.species,
            a.breed,
            COALESCE(a.is_deleted, 0)                   AS animal_deleted,
            CONCAT(s.first_name, ' ', s.last_name)    AS reviewed_by_name
        FROM   Foster  f
        JOIN   Person  p  ON f.person_id  = p.person_id
        JOIN   Animal  a  ON f.animal_id  = a.animal_id
        LEFT JOIN Staff s ON f.reviewed_by = s.staff_id
        WHERE  f.status = 'approved'
        ORDER  BY f.start_date DESC, f.submitted_at DESC
        """
    )
    fosters = cursor.fetchall()

    cursor.execute(
        """
        SELECT
            r.rescue_id,
            r.rescue_date,
            r.location,
            r.animal_species,
            r.photo_url,
            r.submitted_at,
            r.notes,
            CONCAT(p.first_name, ' ', p.last_name)   AS rescuer_name,
            COALESCE(
                (SELECT pc.contact_value FROM Person_Contact pc
                 WHERE pc.person_id = p.person_id AND pc.contact_type = 'email' LIMIT 1),
                (SELECT pc.contact_value FROM Person_Contact pc
                 WHERE pc.person_id = p.person_id AND pc.contact_type = 'phone' LIMIT 1)
            )                                           AS rescuer_contact,
            r.animal_id,
            COALESCE(a.name, r.animal_name_snapshot, 'Unknown') AS animal_name,
            COALESCE(a.is_deleted, 0)                   AS animal_deleted,
            a.status                                    AS animal_status,
            CONCAT(s.first_name, ' ', s.last_name)    AS reviewed_by_name
        FROM   Rescue  r
        JOIN   Person  p  ON r.person_id   = p.person_id
        LEFT JOIN Animal a ON r.animal_id  = a.animal_id
        LEFT JOIN Staff  s ON r.reviewed_by = s.staff_id
        WHERE  r.status = 'approved'
        ORDER  BY r.rescue_date DESC, r.submitted_at DESC
        """
    )
    rescues = cursor.fetchall()

    cursor.execute(
        """
        SELECT
            r.rescue_id,
            r.rescue_date,
            r.location,
            r.animal_species,
            r.photo_url,
            r.submitted_at,
            r.notes,
            CONCAT(p.first_name, ' ', p.last_name)   AS rescuer_name,
            r.animal_id,
            COALESCE(a.name, r.animal_name_snapshot)   AS animal_name,
            a.status                                   AS animal_status
        FROM   Rescue  r
        JOIN   Person  p  ON r.person_id = p.person_id
        LEFT JOIN Animal a ON r.animal_id = a.animal_id
        WHERE  r.status = 'pending'
        ORDER  BY r.submitted_at ASC
        """
    )
    rescuing = cursor.fetchall()

    return render_template(
        "staff/logbook.html",
        adoptions=adoptions,
        fosters=fosters,
        rescues=rescues,
        rescuing=rescuing,
    )