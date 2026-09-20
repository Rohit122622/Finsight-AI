# FinSentry AI — Secret Rotation Checklist

**Status:** CHECKLIST ONLY. **No credentials have been rotated.** This document records where secrets live, confirms none are committed, and provides the manual rotation procedure to run when going to production. Rotation itself is a **MANUAL PRODUCTION STEP** performed by the operator.

**Last scanned (local, masked):** 2026-09-20.

---

## 1. Secret exposure scan (result)

Masked scan of the working tree (excluding `venv/`, `node_modules/`, `dist/`, `.git/`, `.storage/`; git-ignored `.env` files are not tracked):

| Check | Pattern | Result |
|---|---|---|
| Groq keys in tracked source | `gsk_…` | None |
| Google API keys in tracked source | `AIzaSy…` | None |
| Google OAuth client secrets | `GOCSPX-…` | None |
| Mongo SRV URI with inline creds | `mongodb+srv://user:pass@…` | Only the `<user>:<password>` **placeholder** in `backend/.env.example` (not a secret) |
| Frontend secret leakage | `VITE_*SECRET/KEY/PASSWORD/TOKEN` | None |

**Frontend env vars in use:** `VITE_API_BASE_URL` (`/api/v1`) and `VITE_BACKEND_URL` (dev proxy target). Both are **non-secret URLs**. No API keys or credentials are shipped to the client bundle.

**Git status (from Part C):** `backend/.env`, `.env`, and `frontend/.env` are git-ignored; no non-example `.env` is tracked; `backend/.env` has never been committed; history is clean.

---

## 2. Secret inventory (masked — names only, no values)

Live secret values currently reside **only** in the local, git-ignored `backend/.env`. Names and destinations:

| Secret (env key) | Purpose | Managed destination for production |
|---|---|---|
| `MONGODB_URI` | MongoDB Atlas connection (contains user:pass) | Render dashboard (`sync: false`) |
| `JWT_SECRET_KEY` | Signs/verifies access & refresh tokens | Render dashboard (`sync: false`) |
| `GOOGLE_CLIENT_ID` | Google OAuth client | Render dashboard (`sync: false`) |
| `GOOGLE_CLIENT_SECRET` | Google OAuth secret | Render dashboard (`sync: false`) |
| `GROQ_API_KEY` | Groq LLM provider | Render dashboard (`sync: false`) |
| `GOOGLE_API_KEY` | Google (Gemini) LLM provider | Render dashboard (`sync: false`) |
| `OLLAMA_API_KEY` | Ollama Cloud LLM provider (default) | Render dashboard (`sync: false`) |
| `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` / `R2_ACCOUNT_ID` | Cloudflare R2 object storage | Render dashboard (`sync: false`) |
| `SMTP_USERNAME` / `SMTP_PASSWORD` | Gmail SMTP (app password) — **already verified; do not modify** | Render dashboard (`sync: false`) |
| `PDF_SECRET_KEY` (optional) | Encrypts per-report PDF password at rest | Render dashboard (`sync: false`); if unset, derived from `JWT_SECRET_KEY` |

> Values are intentionally omitted. When reporting, reference secrets by key name only.

---

## 3. Rotation procedure (MANUAL PRODUCTION STEP — not executed here)

Rotate **before** first production go-live, and on any suspected exposure. General rule: provision the new secret at the provider first, update the deployment env, verify, then revoke the old one.

**MongoDB (`MONGODB_URI`)**
1. Atlas → Database Access → create a new DB user (or reset password).
2. Update `MONGODB_URI` in Render (backend + worker).
3. Redeploy; verify `GET /api/v1/health` and an authenticated read.
4. Delete/disable the old DB user.

**JWT (`JWT_SECRET_KEY`)**
1. Generate: `python -c "import secrets; print(secrets.token_urlsafe(64))"`.
2. Update in Render (backend + worker — must match).
3. Redeploy. Note: rotating invalidates all existing sessions (users re-login). If `PDF_SECRET_KEY` is unset, this also changes the derived PDF key — set an explicit `PDF_SECRET_KEY` first if PDF passwords must remain decryptable.

**Google OAuth (`GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`)**
1. Google Cloud Console → Credentials → reset client secret.
2. Confirm authorized redirect URIs include the production `GOOGLE_REDIRECT_URI`.
3. Update in Render; redeploy; test a full login round-trip.

**LLM provider keys (`GROQ_API_KEY`, `GOOGLE_API_KEY`, `OLLAMA_API_KEY`)**
1. Create a new key in the provider console.
2. Update in Render (backend + worker); redeploy.
3. Verify an extraction/research run; revoke the old key.

**Cloudflare R2 (`R2_*`)**
1. R2 → Manage API Tokens → create new token; update `R2_ACCESS_KEY_ID`/`R2_SECRET_ACCESS_KEY` (and account/endpoint if changed).
2. Update in Render; redeploy; verify an upload + download.
3. Revoke the old token.

**SMTP (`SMTP_PASSWORD`)** — Gmail is verified working; rotate **only** if compromised.
1. Google Account → App passwords → generate new.
2. Update `SMTP_PASSWORD` in Render; redeploy; send one test email.
3. Revoke the old app password. Do not alter SMTP host/port/architecture.

---

## 4. Post-deployment hardening review (DOCUMENTED — not changed)

The following are current code defaults reviewed for production. **No code was modified**; these are recommendations for the operator to apply via env/config at deploy time.

| Item | Current default | Production recommendation |
|---|---|---|
| `DEBUG` | `False` in code | Keep `false` in prod (`render.yaml` sets `"false"`). Never enable in prod. |
| `APP_ENV` | `development` | Set `production` (render.yaml does). |
| CORS | `get_cors_origins()` = `CORS_ORIGINS` + `FRONTEND_URL` | Set `FRONTEND_URL` to the exact deployed origin; add extra origins via `CORS_ORIGINS`. Avoid wildcards. |
| `JWT_SECRET_KEY` | required, no default | Use a fresh 64-byte urlsafe secret in prod, distinct from any dev value. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 30 | Reasonable; shorten if higher assurance needed. |
| Redis exposure | `render.yaml` `ipAllowList: []` | Keep empty (reachable only from Render services; no public access). |
| `SCANNER_FAIL_CLOSED` | `True` | If `CLAMAV_ENABLED=true`, keep fail-closed so unscanned uploads are rejected. |
| Secrets in VCS | none tracked | Keep `.env` git-ignored; use dashboard secrets (`sync: false`). |

> These are advisory. Applying them (e.g., tightening token lifetimes) is a deliberate operator decision, not part of this cleanup.
