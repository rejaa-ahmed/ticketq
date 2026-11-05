# TicketQ – Event Booking Prototype (architecture feasibility demo)

A small working prototype of the event/ticket booking architecture
(3-tier + event-driven). Components stand in for the cloud services:

| Prototype component | Stands in for (cloud design) |
|---|---|
| HTML pages (`templates/`, `public/static/`) | Frontend (S3 + CloudFront) |
| Flask REST API (`app.py`) | API Gateway + backend service |
| Postgres via `DATABASE_URL` (Supabase), else SQLite (`db.py`) | Amazon RDS (PostgreSQL) |
| In-process TTL cache (`cache.py`) | ElastiCache (Redis) |
| `jobs` table: visibility timeout, retries, DLQ (`db.py`) | Amazon SQS + dead-letter queue |
| Worker (`worker.py`, `POST /api/worker/run`) | AWS Lambda (+ SES for email) |

The booking and its `BookingCreated` message are written in **one transaction**
(outbox pattern), so a booking can never exist without its message.

## Run locally

```powershell
cd prototype
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python app.py
```

Open http://localhost:5000. Locally a background thread also polls the queue;
on Vercel the worker runs only through `POST /api/worker/run`.

## Demo script

1. **Events page** – note "served from: database", refresh → "cache".
2. Book a seat → API responds immediately (202, *Pending*); the cache is invalidated.
3. **My Bookings** – after ~3 s the worker confirms it and a ticket code appears
   (the "email" is printed in the server log).
4. Book the last seat of an event → it shows *Sold out*; extra attempts are rejected (no double-selling).
5. Tick **Simulate email service outage**, make a booking → it still succeeds but
   stays *Pending*; after 3 failed attempts the message lands in the **DLQ**.
6. Untick the outage, click **Re-drive DLQ** → the booking gets confirmed.

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/events` | List events (cached) |
| POST | `/api/bookings` | Reserve a seat + queue BookingCreated (one transaction) |
| GET | `/api/bookings?email=` | List bookings |
| POST | `/api/worker/run` | One worker invocation: process due messages |
| GET | `/api/system` | Queue / DLQ / cache stats |
| POST | `/api/system/failure` | Toggle simulated email outage |
| POST | `/api/system/redrive` | Move DLQ messages back to the queue |

Settings: `DATABASE_URL` (Postgres), `WORKER_DELAY` (seconds of simulated work, default 3).
Delete `booking.db` to reset local data.
