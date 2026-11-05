# TicketQ – Event Booking System (DevOps Assignment)

Software architecture design for an event/ticket booking application:
**3-tier architecture + event-driven asynchronous processing**.

| Folder / file | Contents |
|---|---|
| `deliverables/` | Architecture diagram (`.drawio` + `.png`), 1–2 page report (`.docx`), presentation (`.pptx`) |
| `prototype/` | Working Flask prototype proving the architecture is feasible (see `prototype/README.md`) |

## Deployed architecture (prototype)

| Design (AWS) | Prototype deployment |
|---|---|
| Frontend (S3 + CloudFront) | **Vercel** CDN (static files) + Flask-rendered pages |
| API Gateway + Booking API | Flask on **Vercel** serverless functions |
| Amazon RDS (PostgreSQL) | **Supabase** Postgres |
| Amazon SQS + DLQ | `jobs` table in Supabase Postgres (visibility timeout, retries, DLQ, re-drive) |
| AWS Lambda worker + SES | `POST /api/worker/run` – each call is one serverless worker invocation |
| ElastiCache (Redis) | In-process TTL cache (per function instance) |
| CI/CD | **GitHub** → Vercel auto-deploy on every push |

## Deploying (free, no card)

1. **Supabase** – create a project → **Connect** → **Direct** (connection string) →
   choose **Transaction pooler** (best for serverless; Session pooler also works) → copy the URI and
   put your database password in place of `[YOUR-PASSWORD]`.
   Tables and sample events are created automatically on first request.
2. **Vercel** – sign up with GitHub → **Add New… → Project** → import this repo.
   - **Root Directory:** `prototype`  (Framework preset: Flask / Other)
   - **Environment Variable:** `DATABASE_URL` = the Supabase string
   - **Deploy**.
3. `prototype/vercel.json` runs the functions in Singapore (`sin1`). If your Supabase project is in
   another region, change it to the nearest Vercel region (e.g. `bom1` Mumbai, `fra1` Frankfurt, `iad1` US East).

## Running locally

```powershell
cd prototype
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python app.py      # SQLite + background worker; set DATABASE_URL to use Postgres
```
