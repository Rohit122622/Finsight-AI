# FinSentry AI — Manual Deployment Runbook

**Status:** REFERENCE ONLY — **not executed.** This is the ordered procedure an operator follows to deploy manually. Nothing here has been run; no cloud resources were provisioned and no credentials were rotated.

**Prepared configs this runbook relies on:** `render.yaml`, `frontend/vercel.json`, `docker/backend.Dockerfile`, `docker/celery.Dockerfile`, `docker/frontend.Dockerfile`, `.github/workflows/ci.yml`, `backend/.env.example`.

**Companion docs:** `docs/DEPLOYMENT_READINESS.md`, `docs/SECRET_ROTATION_CHECKLIST.md`, `docs/PHASE_7_KPI_REPORT.md`.

---

## Legend
- **[LOCAL]** run on the operator's machine
- **[PROVIDER]** action in a provider dashboard/console
- **[VERIFY]** confirmation step — do not proceed until it passes

---

## Phase 0 — Pre-flight (local)

1. **[LOCAL]** Confirm `main` is green in CI (backend tests + frontend build + docker build all pass on GitHub Actions).
2. **[LOCAL]** Confirm working tree is clean and the intended commit is pushed: `git status`, `git log -1`.
3. **[LOCAL]** Confirm no secrets are tracked: `git ls-files | Select-String -Pattern "\.env$"` returns only `*.env.example`. (Verified in Part C.)
4. **[VERIFY]** `backend/.env.example` reflects all required vars (see `backend/core/config.py`). Do **not** commit a real `backend/.env`.

## Phase 1 — External managed services (provider)

5. **[PROVIDER]** MongoDB Atlas: create the production cluster + database user; capture the `MONGODB_URI` (keep secret). Configure network access (allow Render egress or `0.0.0.0/0` only if unavoidable, prefer specific).
6. **[PROVIDER]** Cloudflare R2: create the `finsentry-documents` bucket; generate an API token; capture `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`.
7. **[PROVIDER]** Google Cloud Console: confirm OAuth client; add the production redirect URI (matches `GOOGLE_REDIRECT_URI` you will set). Capture `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`.
8. **[PROVIDER]** LLM providers: confirm at least one key is active (`OLLAMA_API_KEY` default provider; optionally `GROQ_API_KEY` / `GOOGLE_API_KEY`).
9. **[PROVIDER]** Gmail SMTP: **already verified working — do not modify.** Just confirm `SMTP_USERNAME` / `SMTP_PASSWORD` (app password) are available to set as secrets.

## Phase 2 — Backend + worker + Redis (Render)

10. **[PROVIDER]** Connect the Git repo to Render and apply the `render.yaml` blueprint. This provisions: `finsentry-backend` (web), `finsentry-worker` (worker), `finsentry-redis` (managed Redis).
11. **[PROVIDER]** In the Render dashboard, set every `sync: false` secret for **both** the web and worker services: `MONGODB_URI`, `JWT_SECRET_KEY`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`, `GROQ_API_KEY`, `GOOGLE_API_KEY`, `OLLAMA_API_KEY`, `R2_*`, and (SMTP for the web service). `JWT_SECRET_KEY` must be identical across web + worker.
12. **[PROVIDER]** Generate a fresh production `JWT_SECRET_KEY`: `python -c "import secrets; print(secrets.token_urlsafe(64))"` — distinct from any dev value.
13. **[VERIFY]** Confirm `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND` are auto-wired from `finsentry-redis` (via `fromService`) on both services.
14. **[PROVIDER]** Leave `FRONTEND_URL` unset for now (set it after the frontend URL is known, Phase 4).
15. **[PROVIDER]** Trigger the first deploy of `finsentry-backend` and `finsentry-worker` (Docker builds from `docker/backend.Dockerfile` and `docker/celery.Dockerfile`).
16. **[VERIFY]** Backend health: `GET https://<backend-host>/api/v1/health` → `200`. Also `GET /openapi.json` → `200`.
17. **[VERIFY]** Worker: Render worker logs show Celery started; `celery -A workers.celery_app inspect ping` responds (or `CELERY_INSPECT=1 python scripts/kpi_probe.py`).

## Phase 3 — Database initialization

18. **[LOCAL/PROVIDER]** Create indexes once against the production DB: `python scripts/create_indexes.py` with the production `MONGODB_URI` in the environment. Run from a trusted host with network access to Atlas.
19. **[VERIFY]** Confirm indexes exist (Atlas UI or `create_indexes.py` output). This is idempotent; re-running is safe.

## Phase 4 — Frontend (Vercel)

20. **[PROVIDER]** Import the repo into Vercel with root = `frontend/`. `vercel.json` sets framework=vite, `npm ci`, `npm run build`, output `dist/`, SPA rewrite, and security headers.
21. **[PROVIDER]** Set frontend env: `VITE_API_BASE_URL` to the backend API base (e.g. `https://<backend-host>/api/v1`). (`VITE_BACKEND_URL` is dev-proxy only.) Deploy.
22. **[VERIFY]** Frontend loads; static assets serve; deep links resolve via SPA rewrite.

## Phase 5 — Wire origins + auth

23. **[PROVIDER]** Set `FRONTEND_URL` (and any extra `CORS_ORIGINS`) on the backend to the deployed Vercel origin; redeploy backend. `get_cors_origins()` always includes `FRONTEND_URL`.
24. **[PROVIDER]** Confirm the Google OAuth authorized redirect URI exactly matches the production `GOOGLE_REDIRECT_URI`.
25. **[VERIFY]** Full Google OAuth login round-trip from the deployed frontend succeeds.

## Phase 6 — Post-deploy smoke + observability

26. **[VERIFY]** `python scripts/kpi_probe.py --base-url https://<backend-host> --log` → all components `ok`. This begins accumulating uptime data in `kpi_probe_history.jsonl`.
27. **[VERIFY]** End-to-end: upload a document → extraction → report generation → download → (optional) email delivery via the verified Gmail SMTP.
28. **[PROVIDER]** Schedule the probe (cron/uptime monitor) at a fixed interval to build the uptime observation window. Do not report an uptime percentage until enough observations exist.

---

## Rollback (if any VERIFY fails)

- **Backend/worker (Render):** roll back to the previous successful deploy in the service's Deploys tab. If a bad commit auto-deployed, revert the commit on `main` or pause `autoDeploy`.
- **Frontend (Vercel):** promote the previous deployment (instant).
- **Env/config regressions:** re-set the prior value in the dashboard and restart — no rebuild needed.
- **Data:** rely on Atlas point-in-time restore and R2 object versioning (configure retention before go-live).

## Hard constraints (do not violate during deploy)

- Do **not** modify Gmail SMTP credentials or the Celery email architecture.
- Do **not** change Extraction, Red Flag, Comparison, or Research/RAG logic.
- Do **not** enable `DEBUG` in production (`render.yaml` sets `"false"`).
- Keep `.env` files out of version control; use dashboard secrets (`sync: false`).
