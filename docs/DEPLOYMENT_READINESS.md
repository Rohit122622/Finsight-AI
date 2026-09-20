# FinSentry AI — Deployment Readiness

**Status:** PREPARATION ONLY. Nothing in this document has been deployed. No cloud connectivity, credential rotation, or production provisioning has been performed. Items requiring live infrastructure are marked **MANUAL PRODUCTION STEP**.

**Last validated (config review, local):** 2026-09-20.

---

## 1. Topology

| Component | Runtime | Source config | Hosting target (prepared) |
|---|---|---|---|
| Frontend (Vite/React SPA) | Static build | `frontend/vercel.json`, `docker/frontend.Dockerfile` | Vercel (or nginx container) |
| Backend API (FastAPI) | Docker | `docker/backend.Dockerfile`, `render.yaml` (`type: web`) | Render web service |
| Celery worker | Docker | `docker/celery.Dockerfile`, `render.yaml` (`type: worker`) | Render worker service (SEPARATE from web) |
| Redis (broker + result backend + cache) | Managed | `render.yaml` (`type: redis`) | Render managed Redis |
| MongoDB | External managed | credentials via `MONGODB_URI` | MongoDB Atlas (**MANUAL PRODUCTION STEP**) |
| Cloudflare R2 (object storage) | External managed | `R2_*` vars | Cloudflare R2 (**MANUAL PRODUCTION STEP**) |
| SMTP / email | External managed | `SMTP_*` vars | Gmail SMTP (already verified working — DO NOT modify) |

> The Celery worker runs as a **separate service** from the web API (confirmed in `render.yaml`). Do not collapse them into one process.

---

## 2. Config validation (what was checked)

All checks below are static config reviews on the local repo. No remote apply was run.

| File | Result | Notes |
|---|---|---|
| `render.yaml` | OK | web + worker + redis; `healthCheckPath: /api/v1/health`; all secrets `sync: false` (never committed); Redis wired via `fromService` connectionString; `DEBUG="false"`, `APP_ENV=production`. |
| `docker/backend.Dockerfile` | OK | Multi-stage, non-root `finsentry` user, `EXPOSE 8000`, HEALTHCHECK hits `/api/v1/health`, `uvicorn main:app --workers 2`. |
| `docker/celery.Dockerfile` | OK | Non-root, HEALTHCHECK `celery -A workers.celery_app inspect ping`, CMD `celery -A workers.celery_app worker --concurrency=2`. |
| `docker/docker-compose.yml` / `.prod.yml` | Present | Local + prod compose topologies available. |
| `frontend/vercel.json` | OK | Vite framework, `npm ci` + `npm run build`, SPA rewrite excludes `/api/`, security headers (nosniff, X-Frame-Options DENY, Referrer-Policy). |
| `.github/workflows/ci.yml` | OK | Backend tests (Python 3.13 + Redis 7 service), frontend build (Node 22), Docker build validation for all 3 images. Uses GitHub secrets for MONGODB_URI/GROQ/GOOGLE/R2. |
| `.dockerignore` | See §6 | Verified excludes `.env`, caches, node_modules. |

**Version note:** CI uses Python 3.13 / Node 22 and Dockerfiles use `python:3.13-slim`. Local KPI measurement ran on Python 3.11. Pin the production toolchain to match CI (3.13).

---

## 3. Environment variables

The complete, current template is `backend/.env.example` (regenerated to match `backend/core/config.py`). Categories:

**Required (backend will fail to start without these):**
- `MONGODB_URI`
- `JWT_SECRET_KEY`

**Required for full functionality (feature-gated, empty = feature disabled):**
- Auth: `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`
- LLM: at least one of `OLLAMA_API_KEY` / `GROQ_API_KEY` / `GOOGLE_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` (default provider = `ollama`)
- Storage: `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME` (empty ⇒ local `.storage`/`uploads` fallback)
- Email: `SMTP_HOST`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL` (`is_smtp_configured()` gates sending)

**Infra (set by `render.yaml` from managed Redis):**
- `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`

**Production hardening values (set in dashboard):**
- `APP_ENV=production`, `DEBUG=false`, `FRONTEND_URL=<deployed origin>`, optional `CORS_ORIGINS=<comma-separated>`

> `DEBUG` is parsed as a strict boolean by pydantic. Use `true`/`false` only. A malformed value crashes startup.

**Secrets never committed:** all secret values are provided via the Render dashboard (`sync: false`) or GitHub Actions secrets. `backend/.env` is git-ignored and has never been committed (verified). See `docs/SECRET_ROTATION_CHECKLIST.md`.

---

## 4. Start commands (reference)

| Context | Command |
|---|---|
| Backend (container) | `uvicorn main:app --host 0.0.0.0 --port 8000 --workers 2 --loop uvloop --http httptools` |
| Backend (local dev) | `python -m uvicorn main:app --host 127.0.0.1 --port 8001` (clear any stray `DEBUG` env first) |
| Celery worker | `celery -A workers.celery_app worker --loglevel=info --concurrency=2` |
| Frontend build | `npm ci && npm run build` (output `dist/`) |
| DB indexes | `python scripts/create_indexes.py` (**run once against target DB — MANUAL PRODUCTION STEP**) |

---

## 5. Smoke tests (post-deploy — MANUAL PRODUCTION STEP)

Run against the live URL once deployed:

1. `GET /api/v1/health` → `200` (liveness).
2. `GET /openapi.json` → `200` (API mounted).
3. Availability probe: `python scripts/kpi_probe.py --base-url https://<backend-host> --log` → all components `ok`; begins accumulating uptime data in `kpi_probe_history.jsonl`.
4. Redis reachability: confirmed by probe (`redis` component) and by worker HEALTHCHECK.
5. Celery worker: `CELERY_INSPECT=1 python scripts/kpi_probe.py` or `celery -A workers.celery_app inspect ping` → worker responds.
6. Auth round-trip: Google OAuth login against the deployed `GOOGLE_REDIRECT_URI`.
7. End-to-end: upload a document → extraction → report generation → (optional) email delivery.

> Uptime remains **NOT MEASURED** until the probe has run over a real observation window in production. Do not claim any uptime percentage before then.

---

## 6. Ignore hygiene (see also Part S/T)

- `.dockerignore` must exclude: `.env`, `__pycache__`, `.pytest_cache`, `node_modules`, `.storage`, `uploads`, `venv`. (Verified in Part S/T.)
- `.gitignore` must exclude: env files, caches, `dist/`, `node_modules/`, `kpi_probe_history.jsonl`.

---

## 7. Rollback plan (prepared)

- **Render (backend/worker):** each deploy is a versioned image. Roll back via Render dashboard → service → "Rollback" to the previous successful deploy. Autodeploy (`autoDeploy: true`) means a bad merge to `main` triggers a deploy — pause autodeploy or revert the commit to recover.
- **Vercel (frontend):** promote the previous deployment from the Vercel dashboard (instant, atomic).
- **Config-only regressions:** env var changes are dashboard-side and reversible without a rebuild; re-set the prior value and restart the service.
- **Data:** MongoDB Atlas point-in-time restore and R2 object versioning are external — configure retention before go-live (**MANUAL PRODUCTION STEP**).

---

## 8. Readiness summary

| Area | State |
|---|---|
| Deploy configs present & internally consistent | READY |
| `backend/.env.example` complete vs `config.py` | READY (regenerated) |
| Secrets kept out of VCS | READY (verified) |
| Health check + availability probe | READY |
| CI (tests + build + docker) | READY |
| Actual cloud provisioning / apply | NOT DONE — MANUAL PRODUCTION STEP |
| Credential rotation | NOT DONE — see SECRET_ROTATION_CHECKLIST |
| Uptime measurement | NOT MEASURED |
