"""Regression test for the JWT algorithm guard (backend/app/auth.py).

Background: the local Supabase stack ships with the Supabase CLI's HS256
JWT secret, which is PUBLIC. To stop that secret forging logins once the app
is on the internet, the project signs user access tokens with an asymmetric
ES256 key (supabase/signing_keys.json), and the backend refuses any token
whose header algorithm is symmetric (HS*) or `none`.

This test asserts:
  1. A real, ES256-signed access token from GoTrue is accepted.
  2. The access tokens GoTrue issues are ES256 (not HS256).
  3. A token carrying an HS256 header is rejected by the backend with 401 —
     built here with a THROWAWAY secret, because the guard decides on the
     header algorithm alone and never needs the real default secret.
  4. A `none`-algorithm (unsigned) token is rejected with 401.

Prereqs: backend on 127.0.0.1:8000, local Supabase running with the ES256
signing key configured.  Run:  python scripts/verify_jwt_alg_guard.py
"""
import base64
import hashlib
import hmac
import json
import os
import sys
import uuid

import httpx
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "backend", ".env"))
SUPABASE_URL = os.environ["SUPABASE_URL"]
SECRET_KEY = os.environ["SUPABASE_SECRET_KEY"]
API = os.environ.get("API", "http://127.0.0.1:8000")
admin = {"apikey": SECRET_KEY, "Authorization": f"Bearer {SECRET_KEY}"}
failures = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail and not ok else ""))
    if not ok:
        failures.append(name)


def _b64(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def make_hs256(claims, secret):
    """An HS256-header token signed with `secret`. Used only to prove the
    backend rejects symmetric-algorithm tokens on header inspection."""
    h = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    p = _b64(json.dumps(claims).encode())
    sig = _b64(hmac.new(secret, f"{h}.{p}".encode(), hashlib.sha256).digest())
    return f"{h}.{p}.{sig}"


def make_none(claims):
    h = _b64(json.dumps({"alg": "none", "typ": "JWT"}).encode())
    p = _b64(json.dumps(claims).encode())
    return f"{h}.{p}."


def main():
    email, pw = f"jwtguard-{uuid.uuid4().hex[:8]}@example.com", "Jg-" + uuid.uuid4().hex[:14]
    uid = httpx.post(f"{SUPABASE_URL}/auth/v1/admin/users", headers=admin,
                     json={"email": email, "password": pw, "email_confirm": True}, timeout=15).json()["id"]
    try:
        tok = httpx.post(f"{SUPABASE_URL}/auth/v1/token?grant_type=password", headers={"apikey": SECRET_KEY},
                         json={"email": email, "password": pw}, timeout=15).json()["access_token"]
        alg = json.loads(base64.urlsafe_b64decode(tok.split(".")[0] + "==")).get("alg")
        check("GoTrue issues ES256 access tokens (not the public HS256 secret)", alg == "ES256", f"alg={alg}")

        r = httpx.get(f"{API}/api/organizations/me", headers={"Authorization": f"Bearer {tok}"}, timeout=20)
        check("real ES256 token is accepted by the backend", r.status_code in (200, 403),
              f"{r.status_code} {r.text[:120]}")  # 403 only if no org; 401 would mean the guard broke real auth

        # A forged-looking HS256 token for this real user id, signed with a
        # throwaway secret. If the guard works it never reaches signature
        # checking — it is refused on the header algorithm alone.
        forged = make_hs256({"sub": uid, "role": "authenticated", "email": email,
                             "aud": "authenticated", "exp": 9999999999}, os.urandom(32))
        r = httpx.get(f"{API}/api/organizations/me", headers={"Authorization": f"Bearer {forged}"}, timeout=20)
        check("HS256 token is rejected with 401", r.status_code == 401, f"{r.status_code} {r.text[:120]}")

        unsigned = make_none({"sub": uid, "role": "service_role", "exp": 9999999999})
        r = httpx.get(f"{API}/api/organizations/me", headers={"Authorization": f"Bearer {unsigned}"}, timeout=20)
        check("unsigned (alg=none) token is rejected with 401", r.status_code == 401, f"{r.status_code}")
    finally:
        m = httpx.get(f"{SUPABASE_URL}/rest/v1/organization_members?user_id=eq.{uid}&select=organization_id",
                      headers=admin, timeout=15).json()
        for row in m:
            httpx.delete(f"{SUPABASE_URL}/rest/v1/organizations?id=eq.{row['organization_id']}", headers=admin, timeout=15)
        httpx.delete(f"{SUPABASE_URL}/auth/v1/admin/users/{uid}", headers=admin, timeout=15)

    print()
    if failures:
        print(f"{len(failures)} check(s) FAILED")
        sys.exit(1)
    print("All JWT algorithm-guard checks passed.")


if __name__ == "__main__":
    main()
