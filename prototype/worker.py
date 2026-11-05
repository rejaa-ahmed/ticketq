"""Async tier: an in-memory queue + background thread standing in for
Amazon SQS + AWS Lambda (+ SES for email).

Flow: API publishes a "BookingCreated" message -> queue -> worker consumes it,
generates a ticket, "sends" the confirmation email and marks the booking
CONFIRMED. Failed messages are retried; after MAX_ATTEMPTS they move to a
dead-letter queue (DLQ) and can be re-driven once the problem is fixed.
"""
import queue
import secrets
import threading
import time

import db

MAX_ATTEMPTS = 3
PROCESSING_DELAY = 3  # seconds, makes the async step visible in the demo
RETRY_DELAY = 2

booking_queue = queue.Queue()
dead_letter_queue = []
state = {"simulate_failure": False, "processed": 0, "failed_attempts": 0}
_lock = threading.Lock()


def publish_booking_created(booking_id):
    booking_queue.put({"type": "BookingCreated", "booking_id": booking_id, "attempts": 0})


def _send_email(booking, ticket_code):
    # Stand-in for Amazon SES.
    print(
        f"[email] To: {booking['email']} | Your ticket for '{booking['event_name']}' "
        f"is {ticket_code}"
    )


def _handle(message):
    if state["simulate_failure"]:
        raise RuntimeError("Email service unavailable (simulated)")
    booking = db.get_booking(message["booking_id"])
    if booking is None or booking["status"] == "CONFIRMED":
        return  # idempotent: safe if a message is delivered twice
    time.sleep(PROCESSING_DELAY)
    ticket_code = "TKT-" + secrets.token_hex(3).upper()
    _send_email(booking, ticket_code)
    db.confirm_booking(booking["id"], ticket_code)


def _run():
    while True:
        message = booking_queue.get()
        try:
            _handle(message)
            with _lock:
                state["processed"] += 1
        except Exception as exc:
            message["attempts"] += 1
            with _lock:
                state["failed_attempts"] += 1
            print(f"[worker] booking {message['booking_id']} attempt "
                  f"{message['attempts']} failed: {exc}")
            if message["attempts"] >= MAX_ATTEMPTS:
                with _lock:
                    dead_letter_queue.append(message)
            else:
                threading.Timer(RETRY_DELAY, booking_queue.put, args=(message,)).start()
        finally:
            booking_queue.task_done()


def redrive_dlq():
    with _lock:
        messages = list(dead_letter_queue)
        dead_letter_queue.clear()
    for m in messages:
        m["attempts"] = 0
        booking_queue.put(m)
    return len(messages)


def stats():
    with _lock:
        return {
            "queue_depth": booking_queue.qsize(),
            "dlq_depth": len(dead_letter_queue),
            "processed": state["processed"],
            "failed_attempts": state["failed_attempts"],
            "simulate_failure": state["simulate_failure"],
        }


def start():
    if state.get("started"):
        return  # only one worker thread per process
    state["started"] = True
    threading.Thread(target=_run, daemon=True, name="booking-worker").start()
