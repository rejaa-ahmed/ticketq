# TicketQ – Event Booking System (DevOps Assignment)

Software architecture design for an event/ticket booking application:
**3-tier architecture + event-driven asynchronous processing**.

| Folder / file | Contents |
|---|---|
| `deliverables/` | Architecture diagram (`.drawio` + `.png`), 1–2 page report (`.docx`), presentation (`.pptx`) |
| `prototype/` | Working Flask prototype proving the architecture is feasible (see `prototype/README.md`) |
| `render.yaml` | Render deployment blueprint (CI/CD: every push to `main` redeploys) |

## Deployed architecture (prototype)

| Design (AWS) | Prototype deployment |
|---|---|
| Frontend (S3 + CloudFront) + API (API Gateway + service) | Flask app on **Render** (gunicorn) |
| Amazon RDS (PostgreSQL) | **Supabase** Postgres |
| ElastiCache (Redis) | In-process TTL cache |
| SQS + Lambda + DLQ | In-process queue + worker thread with retries and DLQ |
| CI/CD | **GitHub** → Render auto-deploy |

## Deploying

1. **Supabase** – create a project, then *Connect* → copy the **Session pooler** connection string
   (`postgresql://postgres.<ref>:<password>@aws-…pooler.supabase.com:5432/postgres`).
   Tables and sample events are created automatically on first start.
2. **Render** – *New* → *Blueprint* → pick this GitHub repo. Render reads `render.yaml`
   and asks for `DATABASE_URL`: paste the Supabase string there.
3. Open the `https://ticketq-….onrender.com` URL. Free instances sleep after ~15 min idle,
   so the first request can take ~30–60 s.

## Running locally

```powershell
cd prototype
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python app.py      # SQLite locally; set DATABASE_URL to use Postgres
```
