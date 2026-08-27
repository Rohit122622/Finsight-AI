# FinSentry AI — System Design Specification (Phase 1)

> **Version:** 1.0.0 — Phase 1 Complete  
> **Last Updated:** 2026-08-16

---

## 1. Overview

FinSentry AI is an intelligent financial research analysis platform powered by AI agents. Phase 1 establishes the foundational backend infrastructure and a fully functional frontend UI for authentication and research session management.

## 2. Architecture

### 2.1 Technology Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python 3.11, FastAPI, Motor (async MongoDB driver) |
| **Database** | MongoDB Atlas |
| **Authentication** | JWT (python-jose), bcrypt, Google OAuth2 (Authlib) |
| **Frontend** | React 19, TypeScript 6, Vite 8, Tailwind CSS 4, Zustand |
| **HTTP Client** | Axios (frontend), httpx (test suite) |

### 2.2 Project Structure

```
backend/
├── api/                 # FastAPI route handlers
│   ├── auth.py          # Register, login, refresh, logout, /me
│   ├── google_auth.py   # Google OAuth login/callback
│   └── sessions.py      # Session CRUD endpoints
├── core/
│   └── config.py        # Environment-based settings (pydantic-settings)
├── database/
│   ├── connection.py    # MongoDB Atlas connection manager
│   └── indexes.py       # Index definitions (users, sessions, refresh_tokens)
├── middleware/
│   ├── auth_middleware.py   # JWT Bearer token verification
│   ├── owner_middleware.py  # Session ownership verification
│   └── rate_limiter.py      # In-memory login rate limiter
├── models/
│   ├── user.py          # User document model
│   └── session.py       # Research session document model
├── schemas/
│   ├── auth.py          # Auth request/response schemas
│   └── session.py       # Session request/response schemas
├── services/
│   ├── auth_service.py        # Auth business logic + token revocation
│   ├── google_auth_service.py # Google OAuth processing
│   └── session_service.py     # Session CRUD business logic
├── tests/
│   ├── conftest.py             # Shared test fixtures
│   ├── test_auth.py            # Auth endpoint tests (18 tests)
│   ├── test_google_auth.py     # Google OAuth tests (14 tests)
│   ├── test_sessions.py        # Session CRUD + isolation tests (24 tests)
│   ├── test_token_revocation.py # Refresh token revocation tests
│   └── test_rate_limiting.py    # Login rate limiting tests
└── main.py              # FastAPI application entry-point

frontend/
├── src/
│   ├── api/
│   │   ├── client.ts    # Axios instance with auth + silent refresh
│   │   ├── auth.ts      # Auth API functions
│   │   └── sessions.ts  # Session API functions
│   ├── components/
│   │   └── Toast.tsx    # Toast notification system
│   ├── layouts/
│   │   └── AppLayout.tsx # Sidebar + top nav layout
│   ├── pages/
│   │   ├── Login.tsx          # Email/password + Google login
│   │   ├── Register.tsx       # Registration form
│   │   ├── GoogleCallback.tsx # OAuth callback handler
│   │   ├── Dashboard.tsx      # Session grid + CRUD modals
│   │   └── SessionDetail.tsx  # Session metadata detail view
│   ├── routes/
│   │   └── ProtectedRoute.tsx # Auth guard with hydration
│   ├── store/
│   │   ├── authStore.ts    # Zustand auth state
│   │   └── sessionStore.ts # Zustand session state
│   ├── types/
│   │   └── index.ts     # TypeScript interfaces
│   ├── App.tsx          # Route definitions
│   ├── main.tsx         # React entry point with BrowserRouter
│   └── index.css        # Design system (Verified Ledger palette)
├── index.html
└── vite.config.ts       # Vite config with API proxy
```

## 3. Authentication

### 3.1 JWT Authentication

- **Access tokens**: Short-lived (30 min), HS256-signed, `type=access` claim
- **Refresh tokens**: Long-lived (7 days), HS256-signed, `type=refresh` claim with unique `jti` (JWT ID)
- **Password hashing**: bcrypt with auto-generated salts
- **Token type enforcement**: Access tokens cannot be used as refresh tokens and vice versa

### 3.2 Refresh Token Revocation

Each refresh token contains a unique JTI (JWT ID) claim. When issued, the JTI is stored in the `refresh_tokens` MongoDB collection:

```json
{
  "jti": "uuid-v4-string",
  "user_id": "mongodb-objectid-string",
  "revoked": false,
  "created_at": "2026-08-16T00:00:00Z"
}
```

**Revocation behavior:**
- **Logout** (`POST /auth/logout`): Revokes ALL active refresh tokens for the authenticated user
- **Token refresh** (`POST /auth/refresh`): Implements token rotation — the old refresh token is revoked and a new one is issued
- **Validation**: Before accepting a refresh token, the server checks its JTI against the database. Revoked or unknown JTIs are rejected with 401.

### 3.3 Google OAuth2

- Uses Authlib's `AsyncOAuth2Client` for authorization URL generation and token exchange
- CSRF protection via signed JWT state tokens (10-minute expiry)
- Creates or retrieves users with `provider=google`
- Issues standard JWT access/refresh token pairs (same as local auth)
- Refresh tokens from Google OAuth are also stored for revocation tracking

### 3.4 Login Rate Limiting

In-memory sliding window rate limiter protects the login endpoint against brute-force attacks:

- **Limit**: 5 failed attempts per IP within a 5-minute window
- **Response**: HTTP 429 Too Many Requests when exceeded
- **Reset**: Counter resets on successful login
- **Security**: Does not reveal whether an email exists through rate-limit behavior
- **Phase 2 note**: Will be migrated to Redis-based distributed rate limiting

## 4. Data Models

### 4.1 User Model (`users` collection)

| Field | Type | Description |
|-------|------|-------------|
| `_id` | ObjectId | MongoDB auto-generated |
| `full_name` | string | 1-128 characters |
| `email` | string | Unique, validated email |
| `password_hash` | string | bcrypt hash (empty for Google users) |
| `provider` | enum | `local` or `google` |
| `created_at` | datetime | UTC timestamp |
| `updated_at` | datetime | UTC timestamp |

### 4.2 Session Model (`research_sessions` collection)

| Field | Type | Description |
|-------|------|-------------|
| `_id` | ObjectId | MongoDB auto-generated |
| `user_id` | string | Owner's user ID |
| `session_name` | string | 1-256 characters |
| `created_at` | datetime | UTC timestamp |
| `updated_at` | datetime | UTC timestamp |

### 4.3 Refresh Token Model (`refresh_tokens` collection)

| Field | Type | Description |
|-------|------|-------------|
| `jti` | string | Unique JWT ID (UUID v4) |
| `user_id` | string | Owner's user ID |
| `revoked` | boolean | Revocation status |
| `created_at` | datetime | UTC timestamp |

## 5. Multi-Tenant Session Isolation

All session queries use a compound filter: `{"_id": ObjectId(session_id), "user_id": user_id}`

This ensures:
- User A cannot see User B's sessions in listings
- User A cannot access, rename, or delete User B's sessions
- Unauthorized access returns 404 (not 403) to prevent information leakage

## 6. API Endpoints

### 6.1 Authentication

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/v1/auth/register` | No | Create account, returns token pair |
| POST | `/api/v1/auth/login` | No | Login, returns token pair (rate-limited) |
| POST | `/api/v1/auth/refresh` | No | Exchange refresh token for new pair |
| GET | `/api/v1/auth/me` | Bearer | Get current user profile |
| POST | `/api/v1/auth/logout` | Bearer | Revoke all refresh tokens |

### 6.2 Google OAuth

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/v1/auth/google/login` | No | Redirect to Google OAuth |
| GET | `/api/v1/auth/google/callback` | No | Handle OAuth callback, return token pair |

### 6.3 Sessions

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/v1/sessions` | Bearer | Create session |
| GET | `/api/v1/sessions` | Bearer | List sessions (paginated) |
| GET | `/api/v1/sessions/{id}` | Bearer | Get session by ID |
| PATCH | `/api/v1/sessions/{id}` | Bearer | Rename session |
| DELETE | `/api/v1/sessions/{id}` | Bearer | Delete session |

### 6.4 Health

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/v1/health` | No | Liveness probe |

## 7. Database Indexes

| Collection | Index | Type | Purpose |
|-----------|-------|------|---------|
| `users` | `email` | Unique, ascending | Login/registration lookups |
| `research_sessions` | `user_id` | Ascending | Per-user session listing |
| `research_sessions` | `created_at` | Descending | Chronological sorting |
| `refresh_tokens` | `jti` | Unique, ascending | Token revocation lookups |
| `refresh_tokens` | `user_id` | Ascending | Bulk revocation on logout |

## 8. Frontend

### 8.1 Design System — "Verified Ledger" Palette

| Token | Value | Usage |
|-------|-------|-------|
| `--bg-base` | `#0B1220` | Main app background |
| `--bg-surface` | `#111827` | Cards, panels |
| `--bg-surface-alt` | `#1A2332` | Hover/raised surfaces |
| `--emerald-600` | `#059669` | Primary buttons, active states |
| `--emerald-500` | `#10B981` | Links, accents, success |
| `--amber-500` | `#F59E0B` | Warnings, caution (NOT errors) |
| `--risk-500` | `#EF4444` | **Reserved** — not used in Phase 1 |
| `--text-primary` | `#F1F5F9` | Primary text |
| `--text-secondary` | `#94A3B8` | Secondary text |
| `--border-subtle` | `#232D3F` | Card/input borders |

**Typography**: Inter (Google Fonts), semibold/bold for headings, `font-variant-numeric: tabular-nums` for financial figures.

### 8.2 Pages

1. **`/login`** — Email/password + Google OAuth, inline validation, loading states
2. **`/register`** — Full registration form with password confirmation
3. **`/auth/google/callback`** — OAuth redirect handler
4. **`/dashboard`** — Session grid with create/rename/delete modals and pagination
5. **`/sessions/:sessionId`** — Session detail metadata view (Phase 2/3 shell)

### 8.3 State Management

- **Zustand** for both auth and session state (no mixed patterns)
- Tokens persisted to `localStorage`
- Silent refresh on 401 handled centrally in the Axios interceptor

## 9. Test Coverage

| Test File | Test Count | Coverage |
|-----------|-----------|----------|
| `test_auth.py` | 18 | Register, login, refresh, /me, logout |
| `test_google_auth.py` | 14 | State tokens, redirect, callback, user creation |
| `test_sessions.py` | 24 | CRUD, pagination, multi-tenant isolation |
| `test_token_revocation.py` | New | Refresh token revocation after logout |
| `test_rate_limiting.py` | New | Login rate limiting (429 behavior) |

## 10. Security Considerations

- Passwords never logged or exposed in responses
- `password_hash` excluded from all API responses
- Rate limiting prevents brute-force login attempts
- Refresh tokens revoked server-side on logout
- Token rotation on refresh prevents token reuse
- CSRF-protected OAuth state tokens
- Compound ownership filters prevent cross-tenant access
- 404 (not 403) for unauthorized access prevents information leakage

## 11. Phase 2 Roadmap (NOT implemented)

The following are planned for Phase 2 and are NOT part of the current implementation:

- Redis / Celery for distributed task processing
- Cloudflare R2 for document storage
- Document processing pipeline
- Vector database (embeddings)
- CrewAI agent orchestration
- WebSocket real-time updates
- Agent status dashboard
- Chat interface
- Report generation
- Red-flag severity analysis
