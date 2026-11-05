# TicketQ – Event Booking Prototype (architecture feasibility demo)

A small working prototype of the event/ticket booking architecture
(3-tier + event-driven). Local components stand in for the cloud services:

| Prototype component            | Stands in for (cloud design)        |
|--------------------------------|-------------------------------------|
| HTML pages (`templates/`)      | Frontend (S3 + CloudFront)          |
| Flask REST API (`app.py`)      | API Gateway + backend service       |
| SQLite (`db.py`)               | Amazon RDS (PostgreSQL)             |
| In-memory TTL cache (`cache.py`)| ElastiCache (Redis)                |
| Queue + worker thread (`worker.py`) | SQS + Lambda (+ SES for email), with DLQ |

## Run

```powershell
cd prototype
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python app.py
```

Open http://localhost:5000

## Demo script

1. **Events page** – note "served from: database", refresh → "cache".
2. Book a seat → API responds immediately (202, *Pending*); the cache is invalidated.
3. **My Bookings** – after ~3 s the worker confirms it and a ticket code appears
   (the "email" is printed in the terminal).
4. Book the last seat of an event → it shows *Sold out*; extra attempts are rejected (no double-selling).
5. Tick **Simulate email/worker failure**, make a booking → it still succeeds but
   stays *Pending*; after 3 failed attempts the message lands in the **DLQ**.
6. Untick the failure, click **Re-drive DLQ** → the booking gets confirmed.

## API

| Method | Path                    | Purpose                          |
|--------|-------------------------|----------------------------------|
| GET    | `/api/events`           | List events (cached)             |
| POST   | `/api/bookings`         | Reserve a seat, publish message  |
| GET    | `/api/bookings?email=`  | List bookings                    |
| GET    | `/api/system`           | Queue / DLQ / cache stats        |
| POST   | `/api/system/failure`   | Toggle simulated worker failure  |
| POST   | `/api/system/redrive`   | Move DLQ messages back to queue  |

Note: the prototype queue is in memory, so pending messages are lost on restart;
real SQS is durable. Delete `booking.db` to reset the data.
