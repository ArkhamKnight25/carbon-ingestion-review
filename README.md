# CarbonTrace

Enterprise emissions ingestion prototype. Ingests SAP fuel CSVs, utility electricity CSVs, and corporate travel CSVs; computes CO₂e per record with full audit trail; surfaces analyst review/approve/lock workflow.

## Layout

```
backend/    Django 5 + DRF API
frontend/   React 18 + Vite SPA
samples/    Realistic source CSVs (SAP MB51 German headers, ComEd-style utility, Navan-style travel)
MODEL.md, DECISIONS.md, TRADEOFFS.md, SOURCES.md   Design docs
DEPLOY.md   Railway deployment steps
```

## Quick start (local)

### Backend

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

API: http://localhost:8000  
Admin: http://localhost:8000/admin (admin/admin123)

### Frontend

```powershell
cd frontend
npm install
copy .env.example .env
npm run dev
```

UI: http://localhost:5173 (login: admin/admin123 or analyst/analyst123)

## Sample data

Upload each CSV in `/samples/` to its matching source type in **Upload → CSV file**:

- `sap_fuel_sample.csv` → `SAP fuel movements`
- `utility_electricity_sample.csv` → `Utility electricity`
- `travel_sample.csv` → `Corporate travel`

Each file is designed to exercise both happy-path and edge cases (negative quantities, missing plant codes, unknown materials, zero-kWh meters, unrecognized IATA codes, missing distances, outliers).

## Deployment

See [DEPLOY.md](DEPLOY.md). Railway one-click: backend service + Postgres plugin + frontend static site.

## Design docs

- [MODEL.md](MODEL.md) — data model and state machine
- [DECISIONS.md](DECISIONS.md) — every source-format and scoping decision with rationale
- [TRADEOFFS.md](TRADEOFFS.md) — three things deliberately not built
- [SOURCES.md](SOURCES.md) — research per source + what breaks in production

## Credentials (seeded)

- `admin` / `admin123` — superuser, full admin access
- `analyst` / `analyst123` — analyst, can review/approve/lock

Change in production via `SEED_ADMIN_PASSWORD` env var.
