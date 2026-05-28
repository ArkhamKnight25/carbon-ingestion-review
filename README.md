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
Admin: http://localhost:8000/admin

### Frontend

```powershell
cd frontend
npm install
copy .env.example .env
npm run dev
```

UI: http://localhost:5173

## Sample data

Upload each CSV in `/samples/` to its matching source type in **Upload → CSV file**:

- `sap_fuel_sample.csv` → `SAP fuel movements`
- `utility_electricity_sample.csv` → `Utility electricity`
- `travel_sample.csv` → `Corporate travel`

Each file is designed to exercise both happy-path and edge cases (negative quantities, missing plant codes, unknown materials, zero-kWh meters, unrecognized IATA codes, missing distances, outliers).

## Extensibility — what admin can change without a developer

Admin (`/admin/` Django panel) can already CRUD: `Tenant`, `Facility`, `PlantCodeMapping`,
`EmissionFactor`, users, and any `EmissionRecord` row. Plant code mappings also have a
custom Settings page in the SPA so non-technical operators don't need Django admin.

What is deliberately NOT admin-editable:

- **Header alias maps** for each parser (e.g. `Buchungsdatum` → `posting_date`) live as
  Python dicts in `backend/ingestion/parsers.py`. They are the output of source-format
  research and are version-controlled / testable. A production extension would introduce
  a `HeaderAlias(source_type, alias, canonical_field, tenant)` table merged at parse
  time so ops can add new client header variants live; deferred for the prototype
  because hardcoded research output defends more cleanly than a half-built override
  surface.
- **Material → activity-key map** and **cabin → factor map** in the same file, for the
  same reason.
- **Source type enum** (`SAP_FUEL`, `UTILITY_ELEC`, `TRAVEL`). Adding a new source type
  (e.g. waste, refrigerants) requires a new parser function — not a config change.

## Deployment

See [DEPLOY.md](DEPLOY.md). Railway one-click: backend service + Postgres plugin + frontend static site.

## Design docs

- [MODEL.md](MODEL.md) — data model and state machine
- [DECISIONS.md](DECISIONS.md) — every source-format and scoping decision with rationale
- [TRADEOFFS.md](TRADEOFFS.md) — three things deliberately not built
- [SOURCES.md](SOURCES.md) — research per source + what breaks in production

## Credentials

Two users are created at seed time: a superuser (`admin`) and a reviewer (`analyst`).
Production deployments must set `SEED_ADMIN_PASSWORD` in the environment; the seeded
credentials for the live deployment are shared separately with reviewers in the
submission email.
