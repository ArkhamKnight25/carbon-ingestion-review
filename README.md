# CarbonTrace

An emissions ingestion prototype built for the Breathe ESG tech intern assignment. It takes the kind of files a real sustainability lead would forward — an SAP MB51 fuel-movement CSV, a utility portal export, a corporate travel report — normalises them, computes CO₂e per row against DEFRA 2023 factors, and surfaces a review queue where an analyst can approve, flag, edit, or reject each record before the batch is locked for audit. Every change leaves an audit trail.

The interesting bits live in `MODEL.md`, `DECISIONS.md`, `TRADEOFFS.md`, and `SOURCES.md` — that is where the design choices and the things I deliberately did not build are written up.

## Layout

```
backend/    Django 5 + DRF API
frontend/   React 18 + Vite SPA
samples/    Realistic source CSVs (SAP MB51 German headers, ComEd-style utility, Navan-style travel)
render.yaml Render Blueprint (backend + static frontend; DB is external Neon Postgres)
```

## Running it locally

Backend:

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
python manage.py migrate
python manage.py seed
python manage.py runserver
```

API at http://localhost:8000, Django admin at http://localhost:8000/admin/.

Frontend:

```powershell
cd frontend
npm install
copy .env.example .env
npm run dev
```

SPA at http://localhost:5173.

## Sample data

Three CSVs in `samples/` exercise the happy path and the edge cases that show up in real exports — negative quantities, missing plant codes, unknown materials, zero-kWh meters, unrecognised IATA codes, missing distances, outliers. Upload each one to its matching source type from the Upload page.

- `sap_fuel_sample.csv` → SAP fuel movements
- `utility_electricity_sample.csv` → Utility electricity
- `travel_sample.csv` → Corporate travel

Same files are also available at https://drive.google.com/drive/folders/1VVpnoGHBFJQpshWHRaOKpMUgM9cDPemh?usp=sharing if cloning the repo is inconvenient.

## What admin can change without a developer

The Django admin panel at `/admin/` lets a superuser CRUD `Tenant`, `Facility`, `PlantCodeMapping`, `EmissionFactor`, users, and any `EmissionRecord` row. Plant-code mappings also have a dedicated Settings page in the SPA so a non-technical operator does not have to use the Django admin.

A few things are deliberately not admin-editable, and they are all in one place — `backend/ingestion/parsers.py`:

- The header alias maps per source (e.g. `Buchungsdatum` → `posting_date`). These are research output, not configuration, and I would rather have them version-controlled and unit-testable than spread across a per-tenant settings table. A production extension would add a `HeaderAlias(source_type, alias, canonical_field, tenant)` table merged into the parser at runtime, so ops can absorb a new client format without a code change. Deferred for the prototype because hardcoded research output defends more cleanly than a half-built override surface.
- The material → activity-key map and the cabin → factor map, for the same reason.
- The source-type enum itself (`SAP_FUEL`, `UTILITY_ELEC`, `TRAVEL`). Adding a new source type means writing a new parser function, not adding a database row.

## Deployment

Live on Render. See `DEPLOY.md` for the Blueprint walkthrough. The backend is a free Render Python web service running gunicorn against a Neon Postgres instance; the frontend is a free Render static site. Render free tiers sleep services after about 15 minutes of idle, so the first request after a quiet period takes roughly 30-60 seconds. The SPA pings `/api/health/` every ten minutes from any open tab to keep the backend warm during a review session.

## Design docs

- [MODEL.md](MODEL.md) — data model, state machine, audit chain
- [DECISIONS.md](DECISIONS.md) — every ambiguity I resolved and the rationale
- [TRADEOFFS.md](TRADEOFFS.md) — three things I deliberately did not build, with cost estimates
- [SOURCES.md](SOURCES.md) — what I researched for each source and what would break in a real deployment

## Credentials

Two users are created at seed time: a superuser (`admin`) and a reviewer (`analyst`). For the deployed environment, set `SEED_ADMIN_PASSWORD` in the backend env. The seeded credentials for the live deployment are shared with the reviewers in the submission email rather than in this repo.
