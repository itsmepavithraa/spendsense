# SpendSense

[![CI](https://github.com/itsmepavithraa/spendsense/actions/workflows/ci.yml/badge.svg)](https://github.com/itsmepavithraa/spendsense/actions/workflows/ci.yml)

A real-time personal finance app that **automatically categorizes transactions, flags unusual spending with machine learning, and updates live**. Built as a full-stack + data science + cloud project.

> **Status:** feature-complete and tested (130 automated tests, CI on every push). Left to do: add Power BI report screenshots.

> **Privacy note:** the public demo uses synthetic data and a shared demo login. Don't upload a real bank statement to it; run the project locally (see below) if you want to try your own.

## What it does
- Register / log in (JWT authentication)
- Add, view, edit and delete transactions (each user sees only their own data)
- **ML auto-categorization:** a merchant name such as "Swiggy" is labelled *Food & Dining* automatically
- **ML anomaly detection:** an Isolation Forest scores each amount against its category's normal range and flags unusually *large* charges (tiny purchases never raise alerts)
- **Real-time updates:** a WebSocket (`/ws?token=<JWT>`) pushes `transaction.created` and `anomaly.alert` events to the user's open tabs the moment a transaction is saved. Each user only receives their own events.
- **Bank-feed simulator:** `POST /simulate/start` streams random transactions (through the same save + ML path) so a demo always has live data; `POST /simulate/stop` ends it.
- **Live dashboard (Next.js):** login/register, headline stats, spend-by-category donut, monthly trend, an add-transaction form, and a transaction table where new rows appear instantly with a toast alert for unusual charges.
- **Bank statement import:** upload a CSV exported from a bank. The importer finds the header row and columns by itself (separate debit/credit columns or one signed amount, Dr/Cr markers, Indian number formats and day-first dates), keeps spending and ignores deposits, and reduces noisy bank text such as `UPI-SWIGGY-swiggy@icici-4029...` to a merchant name. Rows are categorised and scored in one batch; low-confidence rows stay *Uncategorized* instead of being guessed. Re-uploading a statement never creates duplicates (also under concurrent uploads, via a per-user lock), and the page shows exactly what was imported, skipped and ignored. A sample file is in `frontend/public/sample-statement.csv`.
- **Teach it once (category memory):** real statements are full of small shops no model has seen. A "Needs a category" panel lists the shops the app wasn't sure about (biggest spend first); choose a category once and it is applied to every past transaction from that shop, re-checked for unusual charges, and remembered for all future imports. Categories are decided in this order: your correction, then keyword rules (grocery, provision, bakery, tiffin, metro, gym...), then the ML model, then "Uncategorized" rather than a wrong guess.
- **Subscription detection:** a SQL view finds charges with the same merchant and amount about every month (consistent gaps, 3+ charges) and the dashboard shows the monthly and yearly cost.
- **Pro plan payments (Razorpay, test mode):** the server creates the order and sets the price, Razorpay Checkout takes payment, and the server verifies the HMAC signature before upgrading the user. A signed webhook is the safety net if the browser never calls back; both paths are idempotent. CSV export is the Pro-only feature.
- **Power BI analytics:** five analysis-ready SQL views (`bi_*`) feed a 4-page report. See [docs/powerbi.md](docs/powerbi.md) for the data model, DAX measures and page layouts.

## Tech stack
| Layer | Technology |
|---|---|
| API | FastAPI (Python) |
| Database | PostgreSQL + SQLAlchemy + Alembic migrations |
| Cache / pub-sub | Redis |
| ML | scikit-learn (TF-IDF + Logistic Regression, Isolation Forest) |
| Real-time | WebSockets (FastAPI) |
| Frontend | Next.js 14 (App Router), TypeScript, Tailwind CSS, Recharts |
| Payments | Razorpay (test mode), HMAC-verified checkout and webhook |
| Analytics | SQL views + Power BI |
| Containers | Docker, Docker Compose |
| Tests / CI | pytest, GitHub Actions (SQLite + real PostgreSQL + frontend build) |
| Deployment | Dockerfile + `render.yaml` (Render), Vercel for the frontend |

## Project layout
```
backend/
  app/
    main.py            FastAPI app and router registration
    config.py          settings from environment variables
    database.py        SQLAlchemy engine and sessions
    models.py          database tables
    schemas.py         request / response shapes (Pydantic)
    security.py        bcrypt password hashing and JWT tokens
    deps.py            get_current_user dependency
    services.py        shared "create transaction" logic (ML + save)
    realtime.py        WebSocket connection manager and event builder
    routers/           auth.py, transactions.py, analytics.py, billing.py, merchants.py, ws.py, simulate.py
    importer.py        bank-statement CSV parser and merchant-name cleaner
    categories.py      the category list and merchant-name matching
    ml/                train.py, inference.py, rules.py (keyword rules), artifacts/ (trained models)
  alembic/             database migrations (tables, payments, BI views)
  scripts/seed.py      synthetic transactions + fake sign-ups/purchases
  scripts/export_bi_csv.py   dumps the BI views to CSV for Power BI
  tests/               pytest suite: auth, isolation, ML, WebSockets, payments, analytics
docs/powerbi.md        Power BI build guide
docs/deploy.md         step-by-step deployment (Render + Vercel)
render.yaml            Render blueprint (API + PostgreSQL)
.github/workflows/     CI pipeline
frontend/
  app/                 pages: /login and /dashboard
  components/          stat cards, charts, transaction table, add form, toasts
  lib/                 api.ts (typed client), useLiveFeed.ts (WebSocket hook)
docker-compose.yml     Postgres + Redis + API
```

## Run it locally
1. Copy `.env.example` to `.env` and set the values.
2. Start everything:
   ```bash
   docker compose up -d --build
   ```
3. Create the tables and load demo data:
   ```bash
   docker compose exec api alembic upgrade head
   docker compose exec api python -m scripts.seed
   ```
4. Open the interactive API docs at http://localhost:8000/docs  
   Demo login: `demo@spendsense.com` / `demo12345`
5. Start the dashboard (needs Node 18+):
   ```bash
   cd frontend
   npm install
   npm run dev
   ```
   Open http://localhost:3000, log in with the demo account and click **Simulate bank feed** to watch transactions arrive live.

### Turn on payments (optional)
1. Create a free Razorpay account and switch the dashboard to **Test Mode**.
2. **Account & Settings → API Keys → Generate Test Key**. Put the key id and secret in `.env` as `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET`, then `docker compose up -d api`.
3. Click **Upgrade to Pro** and pay with Razorpay's test card from their docs. Never use real card details in test mode.
4. For the webhook, expose the API with a tunnel (for example ngrok), add `https://<tunnel>/billing/webhook` under **Settings → Webhooks** with events `payment.captured` and `order.paid`, and set `RAZORPAY_WEBHOOK_SECRET` to the secret you chose there.

Without keys the app still runs; billing endpoints answer `503` and the UI explains why.

### Run the tests
```bash
cd backend
pip install -r requirements-dev.txt
python -m pytest tests -q
```
The tests use SQLite and a fake Razorpay (no Docker or internet needed), but they exercise the real signature checks.

To also run them against real PostgreSQL (this enables the subscription-detection and connection-leak tests), create an empty database, apply the migrations to it, and point `TEST_DATABASE_URL` at it. **Use a separate database: the tests empty their tables.**
```bash
export DATABASE_URL=postgresql+psycopg2://user:pass@localhost:5432/spendsense_test
alembic upgrade head
TEST_DATABASE_URL=$DATABASE_URL python -m pytest tests -q
```
CI does exactly this on every push, and also checks that the migrations can be rolled all the way back and re-applied.

### Deploy it
See [docs/deploy.md](docs/deploy.md) for a click-by-click guide (Render for the API and database, Vercel for the frontend, about 30 minutes).

### Retrain the ML models
```bash
docker compose exec api python -m app.ml.train
```

## About the ML numbers
The models are trained on a **synthetic dataset** (~5k transactions) generated by `scripts/seed.py`, where each merchant belongs to one category and anomalies are injected as unusually large amounts. Metrics on this data are therefore optimistic and are not a claim of real-world accuracy.

## Roadmap
- [x] Auth, transaction CRUD, Postgres models, migrations, seed data
- [x] ML categorizer and anomaly detector wired into the API
- [x] Real-time WebSocket feed, live anomaly alerts and bank-feed simulator
- [ ] Redis pub/sub so real-time works across multiple API servers
- [x] Next.js dashboard with live feed, charts and anomaly toasts
- [x] Payments (Pro plan), verified checkout and signed webhook
- [x] Subscription detection and Power BI data layer (SQL views, CSV export, build guide)
- [x] 130 automated tests and a GitHub Actions pipeline (SQLite, PostgreSQL + reversible migrations, frontend build)
- [x] Production container, Render blueprint and deployment guide
- [x] Live demo deployed (Render API + PostgreSQL, Vercel frontend)
- [x] Bank statement CSV import with merchant cleaning, de-duplication and an upload summary
- [ ] Power BI report screenshots
