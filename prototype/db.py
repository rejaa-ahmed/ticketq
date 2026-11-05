"""Data tier.

- Production: Supabase Postgres (stands in for Amazon RDS), used when the
  DATABASE_URL environment variable is set.
- Local development: SQLite file (booking.db), used otherwise.
"""
import os
import sqlite3
from pathlib import Path

DATABASE_URL = os.environ.get("DATABASE_URL")
DB_PATH = Path(__file__).parent / "booking.db"
IS_PG = bool(DATABASE_URL)

if IS_PG:
    import psycopg
    from psycopg.rows import dict_row

SEED_EVENTS = [
    ("Tech Conference 2026", "2026-12-10", "Expo Centre, Karachi", 5),
    ("Live Music Night", "2026-12-18", "Arts Council, Lahore", 3),
    ("Startup Pitch Day", "2027-01-08", "NIC, Islamabad", 10),
]

# Dialect differences, kept in one place.
if IS_PG:
    # Pakistan time (UTC+5, no daylight saving); a fixed offset needs no tz database.
    NOW = "to_char(now() AT TIME ZONE INTERVAL '+05:00', 'YYYY-MM-DD HH24:MI:SS')"
    ID_COL = "id SERIAL PRIMARY KEY"
else:
    NOW = "datetime('now', 'localtime')"
    ID_COL = "id INTEGER PRIMARY KEY AUTOINCREMENT"

SCHEMA = [
    f"""CREATE TABLE IF NOT EXISTS events (
        {ID_COL},
        name TEXT NOT NULL,
        date TEXT NOT NULL,
        venue TEXT NOT NULL,
        seats_left INTEGER NOT NULL CHECK (seats_left >= 0)
    )""",
    f"""CREATE TABLE IF NOT EXISTS bookings (
        {ID_COL},
        event_id INTEGER NOT NULL REFERENCES events(id),
        name TEXT NOT NULL,
        email TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'PENDING',
        ticket_code TEXT,
        created_at TEXT NOT NULL DEFAULT ({NOW}),
        confirmed_at TEXT
    )""",
]


class _Conn:
    """Tiny wrapper so the rest of the code is identical for SQLite and Postgres."""

    def __init__(self):
        if IS_PG:
            # prepare_threshold=None keeps it compatible with Supabase's connection pooler.
            self.c = psycopg.connect(DATABASE_URL, row_factory=dict_row, prepare_threshold=None)
        else:
            self.c = sqlite3.connect(DB_PATH, timeout=10)
            self.c.row_factory = sqlite3.Row

    def run(self, sql, params=()):
        if IS_PG:
            sql = sql.replace("?", "%s")
        return self.c.execute(sql, params)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, *_):
        if exc_type:
            self.c.rollback()
        else:
            self.c.commit()
        self.c.close()


def connect():
    return _Conn()


def init_db():
    with connect() as conn:
        for stmt in SCHEMA:
            conn.run(stmt)
        if conn.run("SELECT COUNT(*) AS n FROM events").fetchone()["n"] == 0:
            for ev in SEED_EVENTS:
                conn.run("INSERT INTO events (name, date, venue, seats_left) VALUES (?, ?, ?, ?)", ev)


def list_events():
    with connect() as conn:
        return [dict(r) for r in conn.run("SELECT * FROM events ORDER BY date")]


def create_booking(event_id, name, email):
    """Reserve a seat atomically. Returns the booking id, or None if sold out.

    The conditional UPDATE (seats_left > 0) is what prevents double-selling
    the last seat when two users book at the same moment.
    """
    with connect() as conn:
        cur = conn.run(
            "UPDATE events SET seats_left = seats_left - 1 WHERE id = ? AND seats_left > 0",
            (event_id,),
        )
        if cur.rowcount == 0:
            return None
        row = conn.run(
            "INSERT INTO bookings (event_id, name, email) VALUES (?, ?, ?) RETURNING id",
            (event_id, name, email),
        ).fetchone()
        return row["id"]


def confirm_booking(booking_id, ticket_code):
    with connect() as conn:
        conn.run(
            f"UPDATE bookings SET status = 'CONFIRMED', ticket_code = ?, confirmed_at = {NOW} WHERE id = ?",
            (ticket_code, booking_id),
        )


def get_booking(booking_id):
    with connect() as conn:
        row = conn.run(
            "SELECT b.*, e.name AS event_name FROM bookings b "
            "JOIN events e ON e.id = b.event_id WHERE b.id = ?",
            (booking_id,),
        ).fetchone()
        return dict(row) if row else None


def list_bookings(email=None):
    sql = (
        "SELECT b.*, e.name AS event_name, e.date AS event_date FROM bookings b "
        "JOIN events e ON e.id = b.event_id"
    )
    params = ()
    if email:
        sql += " WHERE lower(b.email) = lower(?)"
        params = (email,)
    sql += " ORDER BY b.id DESC"
    with connect() as conn:
        return [dict(r) for r in conn.run(sql, params)]
