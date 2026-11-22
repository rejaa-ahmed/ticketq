"""Unit tests. They always use a throwaway SQLite file, never Supabase."""
import os
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

os.environ.pop("DATABASE_URL", None)
os.environ.pop("VERCEL", None)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db
import worker
from cache import cache

# Importing app creates tables and starts the worker, so redirect both first.
_import_dir = tempfile.TemporaryDirectory()
db.DB_PATH = Path(_import_dir.name) / "import.db"
with mock.patch.object(worker, "start"):
    import app as app_module


class TicketQTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        for patcher in (
            mock.patch.object(db, "DB_PATH", Path(tmp.name) / "test.db"),
            mock.patch.object(worker, "PROCESSING_DELAY", 0),
            mock.patch.object(worker, "RETRY_DELAY", -1),  # retries are due immediately
            mock.patch.object(worker, "_send_email"),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        db.init_db()
        cache.invalidate("events")
        self.client = app_module.app.test_client()

    def book(self, **changes):
        data = {"event_id": 1, "name": "Test User", "email": "test@example.com", **changes}
        return self.client.post("/api/bookings", json=data)

    def seats(self):
        return next(e["seats_left"] for e in db.list_events() if e["id"] == 1)

    def set_seats(self, n):
        with db.connect() as conn:
            conn.run("UPDATE events SET seats_left = ? WHERE id = 1", (n,))


class PageTests(TicketQTest):
    def test_pages_load_and_show_version(self):
        for url in ("/", "/bookings"):
            res = self.client.get(url)
            self.assertEqual(res.status_code, 200)
            self.assertIn(f"TicketQ v{app_module.VERSION}", res.get_data(as_text=True))

    def test_stylesheet_is_served(self):
        with self.client.get("/static/style.css") as res:
            self.assertEqual(res.status_code, 200)

    def test_health(self):
        res = self.client.get("/health")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json["status"], "ok")

    def test_version_format(self):
        self.assertRegex(app_module.VERSION, r"^\d+\.\d+(\.\d+)?$")


class BookingTests(TicketQTest):
    def test_booking_is_pending_and_takes_one_seat(self):
        before = self.seats()
        res = self.book()
        self.assertEqual(res.status_code, 202)
        self.assertEqual(res.json["status"], "PENDING")
        self.assertEqual(self.seats(), before - 1)

    def test_booking_queues_one_message(self):
        self.book()
        self.assertEqual(db.job_stats()["queue_depth"], 1)

    def test_invalid_input_is_rejected(self):
        before = self.seats()
        for bad in ({"name": ""}, {"email": "not-an-email"}, {"event_id": "1"}):
            with self.subTest(bad=bad):
                self.assertEqual(self.book(**bad).status_code, 400)
        self.assertEqual(self.seats(), before)

    def test_sold_out_is_rejected_without_a_message(self):
        self.set_seats(0)
        self.assertEqual(self.book().status_code, 409)
        self.assertEqual(db.job_stats()["queue_depth"], 0)

    def test_unknown_event_is_rejected(self):
        self.assertEqual(self.book(event_id=999).status_code, 409)

    def test_last_seat_cannot_be_sold_twice(self):
        self.set_seats(1)
        with ThreadPoolExecutor(8) as pool:
            ids = list(pool.map(lambda _: db.create_booking(1, "A", "a@example.com"), range(8)))
        self.assertEqual(sum(i is not None for i in ids), 1)
        self.assertEqual(self.seats(), 0)

    def test_booking_rolls_back_if_message_cannot_be_queued(self):
        with db.connect() as conn:
            conn.run("DROP TABLE jobs")
        before = self.seats()
        with self.assertRaises(Exception):
            db.create_booking(1, "A", "a@example.com")
        self.assertEqual(self.seats(), before)
        self.assertEqual(db.list_bookings(), [])

    def test_booking_invalidates_event_cache(self):
        self.assertEqual(self.client.get("/api/events").json["source"], "database")
        self.assertEqual(self.client.get("/api/events").json["source"], "cache")
        self.book()
        self.assertEqual(self.client.get("/api/events").json["source"], "database")

    def test_email_filter_ignores_case(self):
        self.book()
        self.book(email="other@example.com")
        res = self.client.get("/api/bookings?email=TEST@example.com")
        self.assertEqual(len(res.json["bookings"]), 1)


class WorkerTests(TicketQTest):
    def test_worker_confirms_booking(self):
        self.book()
        self.assertEqual(worker.run_due(), {"processed": 1, "failed": 0})
        booking = db.list_bookings()[0]
        self.assertEqual(booking["status"], "CONFIRMED")
        self.assertRegex(booking["ticket_code"], r"^TKT-[0-9A-F]{6}$")

    def test_duplicate_message_sends_one_email(self):
        booking_id = self.book().json["booking_id"]
        worker._handle({"booking_id": booking_id})
        worker._handle({"booking_id": booking_id})
        worker._send_email.assert_called_once()

    def test_outage_moves_message_to_dlq_then_redrive_confirms(self):
        self.book()
        worker.set_failure(True)
        with mock.patch("builtins.print"):
            self.assertEqual(worker.run_due()["failed"], worker.MAX_ATTEMPTS)
        self.assertEqual(db.job_stats()["dlq_depth"], 1)
        self.assertEqual(db.list_bookings()[0]["status"], "PENDING")

        worker.set_failure(False)
        self.assertEqual(db.redrive_dlq(), 1)
        worker.run_due()
        self.assertEqual(db.list_bookings()[0]["status"], "CONFIRMED")


if __name__ == "__main__":
    unittest.main()
