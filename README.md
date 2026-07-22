# Recruit AI — Multi-tenant Recruitment Automation SaaS

Six-module recruitment platform (Sourcing, Screening & Scoring, Engagement,
Scheduling, Data/ATS Sync, Reporting) with human-approval gates before any
candidate- or client-facing action.

## Status

| Phase | Scope | Status |
|---|---|---|
| 1 | Foundation: multi-tenant schema + RLS, Supabase Auth, resume scorer | ✅ Verified (isolation + end-to-end scoring) |
| 2 | Sourcing (CSV import, Boolean search) + batch screening + talent pool | ✅ Verified (20-candidate CSV → sensible ranking) |
| 3 | Approval gate 1 + email engagement (Resend) | ✅ Verified (gate enforced; edited in UI; real email sent) |
| 4 | Scheduling (Google Calendar OAuth) | ✅ Verified (real event booked via public link; reminder + nudge fired) |
| 5 | Approval gate 2 + webhook ATS sync + dedup | ✅ Verified (signed webhooks both ways; gate enforced incl. inbound; fuzzy dedup) |
| 6 | Reporting dashboards + weekly PDF summary | ✅ Verified (funnel exact vs seeded data; PII-free client view; PDF valid) |

## Stack

- **Frontend**: React (Vite) + Tailwind v4 — `frontend/`
- **Backend**: FastAPI, modular routers — `backend/app/`
- **DB/Auth**: Supabase (Postgres + RLS, Supabase Auth)
- **AI**: Gemini (`gemini-2.5-flash`) for scoring/extraction
- **PDF**: pdfplumber

## Setup

1. **Apply the database migration**: paste
   `supabase/migrations/0001_phase1_foundation.sql` into the Supabase
   dashboard SQL editor and run it.
2. **Backend**: copy `backend/.env.example` → `backend/.env`, fill keys, then
   ```
   cd backend
   python -m venv .venv && .venv\Scripts\pip install -r requirements.txt
   .venv\Scripts\python -m uvicorn app.main:app --port 8000
   ```
3. **Frontend**: copy `frontend/.env.example` → `frontend/.env`, set the
   **publishable/anon** key (never the secret key), then
   ```
   cd frontend
   npm install && npm run dev
   ```
4. Open http://localhost:5173, sign up (creates your organization).

## Multi-tenancy model

- `organizations` + `organization_members` (join table to `auth.users`)
- Every tenant table (`roles`, `candidates`, `scores`, ...) carries
  `organization_id` with an RLS policy (`is_org_member()`), so direct
  client access is org-scoped at the database layer.
- The backend uses the service key (bypasses RLS) and **must** filter every
  query by the caller's `organization_id`, resolved from their verified JWT
  in `backend/app/auth.py`.

## Verification

With the migration applied and the backend running:

```
backend\.venv\Scripts\python scripts\verify_phase1.py
```

Creates two throwaway users in two orgs and asserts neither can see the
other's data — through the backend API and directly against PostgREST
(exercising RLS itself).

## Scope boundaries (by design)

- **LinkedIn**: no scraping/automation (ToS + no public API). Sourcing works
  via CSV/paste import; `sourcing/connectors/linkedin.py` will be a stub for
  partner-tier LinkedIn Recruiter API access.
- **WhatsApp**: engagement is email-first; WhatsApp adapter will be stubbed
  behind the same interface pending Meta business verification.
- **ATS**: generic webhook interface (Greenhouse/Lever-style); Workday needs
  an enterprise API tier arranged separately.
- **Human approval**: nothing reaches a candidate or client without an
  explicit recruiter click — enforced in every phase.
