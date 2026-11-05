"""Async tier: the ticket worker (stands in for AWS Lambda + Amazon SES).

Messages live in the durable `jobs` table (stands in for Amazon SQS). The
worker claims due messages, generates a ticket, "sends" the email and marks
the booking CONFIRMED. A failed message is retried after RETRY_DELAY seconds;
after MAX_ATTEMPTS it moves to the dead-letter queue (DLQ) until re-driven.

How the worker is triggered:
- On Vercel (serverless): each call to POST /api/worker/run is one worker
  invocation, like one Lambda run. It's called right after a booking and while
  the My Bookings page has messages waiting.
- Locally: a background thread also polls the queue every second.
"""
import os
import secrets
import threading
import time

import db

MAX_ATTEMPTS = 3
PROCESSING_DELAY = float(os.environ.get("WORKER_DELAY", 3))  # makes the async step visible
RETRY_DELAY = 2
VISIBILITY_TIMEOUT = 30
ON_SERVERLESS = bool(os.environ.get("VERCEL"))

_state = {"started": False}


def _send_email(booking, ticket_code):
    # Stand-in for Amazon SES: the "email" appears in the server logs.
    print(f"[email] To: {booking['email']} | Your ticket for '{booking['event_name']}' is {ticket_code}",
          flush=True)


def failure_simulated():
    return db.get_setting("simulate_failure", "0") == "1"


def set_failure(on):
    db.set_setting("simulate_failure", "1" if on else "0")


def _handle(job):
    if failure_simulated():
        raise RuntimeError("Email service unavailable (simulated)")
    booking = db.get_booking(job["booking_id"])
    if booking is None or booking["status"] == "CONFIRMED":
        return  # idempotent: safe if a message is delivered twice
    time.sleep(PROCESSING_DELAY)
    ticket_code = "TKT-" + secrets.token_hex(3).upper()
    _send_email(booking, ticket_code)
    db.confirm_booking(booking["id"], ticket_code)


def run_due(max_jobs=5):
    """Process up to max_jobs due messages. Returns a short summary."""
    processed = failed = 0
    for _ in range(max_jobs):
        job = db.claim_job(VISIBILITY_TIMEOUT)
        if job is None:
            break
        try:
            _handle(job)
            db.complete_job(job["id"])
            processed += 1
        except Exception as exc:
            db.fail_job(job["id"], str(exc), MAX_ATTEMPTS, RETRY_DELAY)
            failed += 1
            print(f"[worker] booking {job['booking_id']} attempt {job['attempts']} failed: {exc}", flush=True)
    return {"processed": processed, "failed": failed}


def redrive_dlq():
    return db.redrive_dlq()


def stats():
    return {**db.job_stats(), "simulate_failure": failure_simulated()}


def _loop():
    while True:
        try:
            if run_due()["processed"] == 0:
                time.sleep(1)
        except Exception as exc:  # keep the local worker alive on transient DB errors
            print(f"[worker] loop error: {exc}", flush=True)
            time.sleep(2)


def start():
    """Start the local background worker (not used on serverless platforms)."""
    if ON_SERVERLESS or _state["started"]:
        return
    _state["started"] = True
    threading.Thread(target=_loop, daemon=True, name="booking-worker").start()
