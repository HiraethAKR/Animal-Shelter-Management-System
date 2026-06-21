import pymysql
import pymysql.cursors
from flask import g, current_app


def get_db():
    """
    Returns a PyMySQL connection for the current request.

    Flask's `g` object is a per-request storage bucket. The first time
    get_db() is called during a request, we open a connection and stash it
    on g. Every later call to get_db() in that SAME request reuses it
    instead of opening a new one.
    """
    if "db" not in g:
        g.db = pymysql.connect(
            host=current_app.config["DB_HOST"],
            port=current_app.config["DB_PORT"],
            user=current_app.config["DB_USER"],
            password=current_app.config["DB_PASSWORD"],
            database=current_app.config["DB_NAME"],
            cursorclass=pymysql.cursors.DictCursor,  # rows come back as dicts, e.g. row["name"]
            autocommit=False,  # we control commits explicitly — safer for multi-step writes
        )
    return g.db


def close_db(e=None):
    """
    Closes the connection stored on g, if one was opened.
    Registered to run automatically at the end of every request (see app/__init__.py).
    """
    db = g.pop("db", None)
    if db is not None:
        db.close()
