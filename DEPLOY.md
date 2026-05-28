# DEPLOY.md — deployment

## Render (recommended, via Blueprint)

`render.yaml` at repo root defines all three services. One-click apply:

1. Sign in at https://render.com → **New** → **Blueprint**
2. Connect this repo
3. Render reads `render.yaml`, provisions:
   - `carbontrace-db` — Postgres
   - `carbontrace-backend` — Django web service
   - `carbontrace-frontend` — static site (Vite build)
4. Prompts for env vars marked `sync: false`:
   - `SEED_ADMIN_PASSWORD` (backend) — strong password for `admin` user
   - `CORS_ALLOWED_ORIGINS` (backend) — leave blank initially, set after frontend deploys
   - `VITE_API_BASE` (frontend) — leave blank initially, set after backend deploys
5. **Apply** — Render builds both services (~5 min)
6. After first deploy:
   - Copy backend URL (e.g. `https://carbontrace-backend.onrender.com`)
   - Set `VITE_API_BASE` on frontend env → triggers frontend rebuild
   - Copy frontend URL (e.g. `https://carbontrace-frontend.onrender.com`)
   - Set `CORS_ALLOWED_ORIGINS` on backend env → triggers backend redeploy

### Notes

- Free Postgres tier on Render is 90 days; after that data is paused. If unavailable at signup, swap `DATABASE_URL` to a free Neon Postgres (`neon.tech`) and remove the `databases:` block from `render.yaml`.
- Free web services sleep after 15 min idle and cold-start in ~30s.

### Smoke test

- `GET https://<backend>.onrender.com/api/health/` → `{"status":"ok"}`
- Login at frontend with `admin` / `<SEED_ADMIN_PASSWORD>`
- Upload three sample CSVs from `/samples/`
- Dashboard shows non-zero scope 1/2/3

---

## Railway (alternative)

Two services on Railway: **Django backend** (web service) + **Postgres** (database plugin). Frontend served separately as a static build (Railway, Vercel, or Netlify).

---

## Prerequisites

- GitHub repo containing this project pushed up (Railway connects via GitHub)
- Railway account (https://railway.app) — free tier covers this prototype

---

## 1. Backend on Railway

### 1.1 Create project + Postgres

1. https://railway.app → **New project** → **Deploy from GitHub repo** → select this repo
2. Railway detects `backend/` as Python; Nixpacks builder runs `pip install -r requirements.txt`
3. In the project dashboard: **+ New** → **Database** → **Add PostgreSQL**
4. Postgres plugin automatically injects `DATABASE_URL` into the web service

### 1.2 Root directory

Settings → **Service Settings** → **Root Directory**: `backend`

### 1.3 Environment variables

Variables tab → add:

```
SECRET_KEY=<generate 50-char random string>
DEBUG=False
ALLOWED_HOSTS=.railway.app
SEED_ADMIN_PASSWORD=<your strong password>
CORS_ALLOWED_ORIGINS=https://<your-frontend-host>
```

Generate a Django secret key:

```python
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

`DATABASE_URL` is auto-injected by the Postgres plugin — do not set manually.

### 1.4 Start command

Already set by [Procfile](backend/Procfile) and [nixpacks.toml](backend/nixpacks.toml):

```
release: python manage.py migrate --noinput && python manage.py seed --noinput
web: gunicorn carbontrace.wsgi --log-file -
```

`migrate` + `seed` run automatically on every deploy.

### 1.5 Generate public domain

Service → **Settings** → **Networking** → **Generate Domain**. Note the URL (e.g. `carbontrace-backend.up.railway.app`).

### 1.6 Smoke test

```
GET https://<backend>.up.railway.app/api/health/   →  {"status":"ok"}
POST https://<backend>.up.railway.app/api/auth/token/   body: {"username":"admin","password":"<your password>"}
```

Admin: `/admin/` — login with `admin` and `SEED_ADMIN_PASSWORD`.

---

## 2. Frontend

Two options. Pick one.

### Option A — Railway static site (simplest, single platform)

1. Railway project → **+ New** → **Empty Service** → connect same GitHub repo
2. Root directory: `frontend`
3. Build command: `npm install && npm run build`
4. Start command: `npx serve -s dist -l $PORT` (requires `serve` in deps — alternatively use Nixpacks defaults)
5. Env var: `VITE_API_BASE=https://<backend>.up.railway.app`
6. **Generate Domain**

### Option B — Vercel / Netlify (recommended for static SPA)

1. Connect repo, root = `frontend`
2. Build: `npm run build`, Output: `dist`
3. Env: `VITE_API_BASE=https://<backend>.up.railway.app`
4. After deploy, copy the frontend URL → add to backend `CORS_ALLOWED_ORIGINS` → redeploy backend

---

## 3. Post-deploy verification checklist

- [ ] `/api/health/` returns `{"status":"ok"}`
- [ ] Login at frontend with `admin` / `<SEED_ADMIN_PASSWORD>` works
- [ ] Upload `samples/sap_fuel_sample.csv` as `SAP_FUEL` → batch shows rows + errors
- [ ] Upload `samples/utility_electricity_sample.csv` as `UTILITY_ELEC` → London HQ March row flagged `zero_value`
- [ ] Upload `samples/travel_sample.csv` as `TRAVEL` → `ZZZ` row in parse errors; missing-distance ground row in parse errors
- [ ] Dashboard shows non-zero Scope 1/2/3 bars
- [ ] Approve a record → audit log shows status_change event
- [ ] Lock a batch where all records approved → batch status = locked, records status = locked

---

## 4. Troubleshooting

**`CSRF verification failed` on admin login over HTTPS**  
`ALLOWED_HOSTS` must include the Railway domain. Already configured via `.railway.app` wildcard in settings.

**`CORS error` from frontend**  
Set backend env `CORS_ALLOWED_ORIGINS=https://<exact-frontend-domain>`. Multiple origins comma-separated.

**`relation "..." does not exist` on first request**  
Migrations did not run. Check release command logs. Manual fix: Railway service → **Run command** → `python manage.py migrate`.

**File upload fails over 50 MB**  
Edit `FILE_UPLOAD_MAX_MEMORY_SIZE` in `settings.py`. Defaults to 50 MB.

**Static files 404 on admin**  
Whitenoise serves them. Ensure `collectstatic` ran (nixpacks.toml). Manual: `python manage.py collectstatic --noinput`.

---

## 5. Rolling back

Railway keeps deploy history. **Deployments** tab → click previous deploy → **Redeploy**. Database is unaffected (migrations not auto-reverted; roll forward with code-fix migrations rather than backward migration).

---

## 6. Production hardening (not in scope for prototype, listed for reviewers)

- Per-tenant authentication (current prototype scopes by first Tenant row — replace with per-user tenant FK)
- Postgres Row-Level Security as defense in depth
- S3 for uploaded file retention (currently in DB only via SHA-256 hash; raw bytes discarded after parse)
- Rate-limit `/api/upload/` (django-ratelimit)
- Send audit log to immutable storage (S3 + Object Lock or Iceberg) for SOX/compliance
- Sentry for error tracking; structured logging to a log aggregator
