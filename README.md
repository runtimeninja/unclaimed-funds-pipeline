# UFIP — Unclaimed Funds Intelligence Pipeline

A four-stage data pipeline that ingests US unclaimed-property records,
normalizes them into a common shape, scores each lead by value/entity-type/
keywords/age, and pushes the highest-priority leads into Airtable. A small
read-only FastAPI backend and single-file dashboard expose the scored leads
for browsing and filtering.

This is an MVP — the pipeline runs end-to-end against a bundled sample
dataset. Live state-by-state ingesters can be plugged in incrementally as
follow-on work.

## Architecture

```
   raw CSV / API responses
            |
            v
+--------------------+      raw_records (JSONB blob, immutable)
|   ingest/          |---->  source-agnostic, BaseIngester subclasses per
+--------------------+       source (CSVFileIngester ships today)
            |
            v
+--------------------+      normalized_records (typed columns + dedup hash)
|   normalize/       |---->  shared parsers (name, entity-type, address,
+--------------------+       claim amount); per-source extract() only
            |
            v
+--------------------+      scored_leads (score + priority + breakdown JSON)
|   score/           |---->  YAML rules at score/config.yaml drive amount
+--------------------+       tiers, entity bonus, keyword bonus, age tiers
            |
   +--------+---------+
   v                  v
+--------+        +-----------+
|  crm/  |        |   api/    |---->  FastAPI + bundled dashboard at /
+--------+        +-----------+       (frontend/index.html)
   |
   v
Airtable (Leads table)
```

Each stage has its own CLI entry point and its own runner. Stages are
idempotent — re-running picks up only the records that haven't been
processed yet.

## Quickstart

Requires Python 3.11+, Docker (for Postgres), and a Bash-compatible shell.

```bash
# 1. Clone and enter the repo
git clone <repo-url> ufip
cd ufip

# 2. Set up Python venv
python -m venv venv
source venv/Scripts/activate        # Windows (Git Bash). Linux/macOS: source venv/bin/activate
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env                # Airtable creds optional; Postgres defaults work as-is

# 4. Start Postgres and run migrations
docker compose up -d
alembic upgrade head

# 5. Run the pipeline against the bundled sample dataset
python -m ingest.cli csv ./data/sample_us_unclaimed.csv --source sample_us_unclaimed
python -m normalize.cli
python -m score.cli

# 6. Launch the API + dashboard
python -m api.cli
# open http://127.0.0.1:8000/
```

The dashboard shows total leads, priority counts, total claim amount, and
a paginated table you can filter by priority / state / minimum amount.
Click any row to see the full score breakdown.

## Project layout

```
ingest/              raw layer — BaseIngester + CSVFileIngester + runner + CLI
normalize/           cleaning layer — BaseNormalizer + shared parsers + runner + CLI
  sources/           one module per real source (sample_us.py today)
score/               scoring layer — YAML-driven rules + runner + CLI
  config.yaml        amount tiers, entity bonus, keyword bonus, age tiers, priority cutoffs
crm/                 export layer — Airtable adapter (pyairtable, lazy-imported)
api/                 FastAPI app — three read-only endpoints, mounts frontend at /
frontend/index.html  dashboard — Tailwind via CDN + vanilla JS
db/                  SQLAlchemy models + session factory, Alembic migrations
data/                sample CSV (only sample_us_unclaimed.csv is committed)
tests/               pytest suite — 69 tests, hits the dev Postgres
```

## API endpoints

All read-only. Bound to `127.0.0.1` by default — set `API_HOST=0.0.0.0`
in `.env` to expose externally (no auth, so do this only on a trusted network).

| Method | Path                  | Purpose                                                   |
| ------ | --------------------- | --------------------------------------------------------- |
| GET    | `/api/leads`          | Paginated list. Filters: `priority`, `state`, `min_amount`, `limit`, `offset` |
| GET    | `/api/leads/{id}`     | Single lead with full score breakdown                     |
| GET    | `/api/stats`          | Counts by priority, total claim amount, export status     |
| GET    | `/`                   | Dashboard (served from `frontend/`)                       |

## Configuration

`.env` (copy from `.env.example`) controls:

- **Postgres**: `DATABASE_URL`, plus `POSTGRES_*` for `docker-compose`
- **Airtable**: `AIRTABLE_API_TOKEN`, `AIRTABLE_BASE_ID`, `AIRTABLE_TABLE_NAME` (only needed if running `crm.cli`)
- **API**: `API_HOST`, `API_PORT`

`score/config.yaml` controls the scoring rules. Edit values, re-run
`python -m score.cli` to re-score un-scored records (or wipe `scored_leads`
to re-score from scratch).

## Tests

```bash
python -m pytest
```

The integration tests hit the dev Postgres on port 5433. They use unique
source identifiers and clean up after themselves so they don't leave state.

If you've seeded the dev DB with the sample dataset (step 5 above), some
integration tests will fail because the dedup hash collides with seeded
content. Clear the seeded data first:

```sql
DELETE FROM raw_records WHERE source = 'sample_us_unclaimed';
```

(Cascades to normalized + scored.)

## Status

MVP-complete:

- Four-stage pipeline runs end-to-end against the bundled sample
- 69 tests passing across all layers
- Airtable export wired up, gated on `.env` credentials
- Dashboard renders scored leads with filtering and detail view

Not in scope yet:

- Live state-by-state ingesters (TX is Cloudflare-Turnstile-gated; other
  states require their own recon)
- Pipeline automation (APScheduler)
- Auth / multi-user / deployment hardening
- Triggering pipeline runs from the dashboard
