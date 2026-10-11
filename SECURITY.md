# Recruit AI — security posture

How the app defends itself when exposed to the internet through a tunnel
(Tailscale Funnel or Cloudflare), and the one step that still needs you.

## Model
- Only the backend (`127.0.0.1:8000`) is exposed through the tunnel. It serves
  the built frontend and is the single door to everything else.
- The browser reaches Supabase only through the backend's `/supabase` proxy,
  which forwards an **allow-list** of GoTrue auth endpoints and nothing else.
  `/pg`, `/mcp`, `/rest`, `/auth/v1/signup`, `/auth/v1/admin`, and path-traversal
  attempts all return 404.
- Every `/api` route verifies the caller's token and scopes every query to the
  caller's organization. Tenant isolation is enforced by the backend (service
  role + explicit `organization_id` filters) and by Postgres RLS behind it.

## Authentication
- **User access tokens are signed with a per-deployment ES256 key**
  (`supabase/signing_keys.json`, gitignored). The Supabase CLI's default HS256
  secret is public, so the backend additionally **refuses any token whose
  header algorithm is not asymmetric** (HS*/`none` → 401), before it ever
  reaches GoTrue. Rotate the key with `supabase gen signing-key`.
  Regression test: `scripts/verify_jwt_alg_guard.py`.
- Password login, password-reset mail, and email-link verify are **rate-limited
  per real caller IP** at the proxy (login: 10 / 5 min). GoTrue's own limits
  see every request from loopback, so they would otherwise be global.
- Google sign-in has a guard against pre-registered-account takeover while email
  verification is off (`_guard_pre_linked_account` in `backend/app/auth.py`).

## Hardening already in place
- Security headers on every response: CSP (no inline script, `frame-ancestors
  'none'`), `X-Frame-Options: DENY`, `nosniff`, `Referrer-Policy: no-referrer`,
  `Permissions-Policy`, `Cache-Control: no-store` on `/api`, HSTS over HTTPS.
  The server banner and interactive API docs are off.
- Request bodies capped at 12 MB (counted as received, so chunked uploads can't
  skip it); resume PDFs capped at 15 pages.
- ATS webhook URLs are checked against internal/loopback/metadata addresses on
  save and at send time, with redirects disabled (SSRF).
- Admin dashboard is reachable only by `PLATFORM_ADMIN_USER_IDS`; everyone else
  gets 404, so it doesn't advertise its existence. Admin views are metadata
  only — never candidate names, emails, resumes, messages or transcripts.
- With two tunnels active, the trusted client-IP header is chosen by `Host`, so
  a caller can't select the other tunnel's trust rules by sending its headers.
- Keys at rest: each workspace's own AI provider key is Fernet-encrypted; the
  signing key and `.env` are gitignored.

## Still needs you
- **Run `scripts/lock-down-lan.ps1` as Administrator.** `supabase start`
  publishes its ports (54421 gateway, 54422 Postgres, 54423 Studio) on
  `0.0.0.0`, so anyone on the same Wi-Fi/LAN can reach the database directly —
  and the gateway runs unauthenticated SQL. The internet tunnel does not expose
  these, but the local network does. The script blocks inbound 54420–54429
  while leaving the app (loopback) working.
- **Email verification is off** until a sender domain is verified (Resend).
  Until then someone can register an address they don't own — fine for a beta,
  not for storing real candidate data at scale. Turn on `REQUIRE_EMAIL_
  VERIFICATION` once `EMAIL_FROM` is a verified domain.
