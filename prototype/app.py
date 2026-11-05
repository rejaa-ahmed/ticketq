"""Application tier: Flask serves the two pages and the REST API."""
import os
import re

from flask import Flask, jsonify, render_template, request

import db
import worker
from cache import cache

app = Flask(__name__)
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ---------- Presentation tier (pages) ----------
@app.get("/")
def events_page():
    return render_template("events.html", active="events")


@app.get("/bookings")
def bookings_page():
    return render_template("bookings.html", active="bookings")


# ---------- REST API ----------
@app.get("/api/events")
def api_events():
    events = cache.get("events")
    source = "cache"
    if events is None:
        events = db.list_events()
        cache.set("events", events)
        source = "database"
    return jsonify({"events": events, "source": source})


@app.post("/api/bookings")
def api_create_booking():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip()
    event_id = data.get("event_id")
    if not name or not EMAIL_RE.match(email) or not isinstance(event_id, int):
        return jsonify({"error": "Please provide a name, a valid email and an event."}), 400

    booking_id = db.create_booking(event_id, name, email)
    if booking_id is None:
        return jsonify({"error": "Sorry, this event is sold out."}), 409

    cache.invalidate("events")                  # seat count changed
    worker.publish_booking_created(booking_id)  # async: don't wait for email/ticket
    return jsonify({"booking_id": booking_id, "status": "PENDING"}), 202


@app.get("/api/bookings")
def api_list_bookings():
    return jsonify({"bookings": db.list_bookings(request.args.get("email"))})


# ---------- Ops / demo controls ----------
@app.get("/api/system")
def api_system():
    return jsonify({**worker.stats(), "cache_hits": cache.hits, "cache_misses": cache.misses})


@app.post("/api/system/failure")
def api_toggle_failure():
    worker.state["simulate_failure"] = bool((request.get_json(silent=True) or {}).get("on"))
    return jsonify(worker.stats())


@app.post("/api/system/redrive")
def api_redrive():
    return jsonify({"redriven": worker.redrive_dlq()})


# Runs on import, so it works both with `python app.py` and with gunicorn (Render).
db.init_db()
worker.start()

if __name__ == "__main__":
    app.run(debug=False, port=int(os.environ.get("PORT", 5000)))
