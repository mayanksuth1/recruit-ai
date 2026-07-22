"""Phase 1 verification: two orgs cannot see each other's data.

Prereqs: migration 0001 applied, backend running on localhost:8000.
Run:  python scripts/verify_phase1.py
Creates two throwaway users/orgs, a role in each, then asserts isolation
both through the backend API and directly against PostgREST with user
tokens (which exercises the RLS policies themselves).
"""
import os
import sys
import uuid

import httpx
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "backend", ".env"))

SUPABASE_URL = os.environ["SUPABASE_URL"]
SECRET_KEY = os.environ["SUPABASE_SECRET_KEY"]
API = "http://localhost:8000"

admin_headers = {"apikey": SECRET_KEY, "Authorization": f"Bearer {SECRET_KEY}"}
failures = []


def check(name: str, ok: bool, detail: str = ""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail and not ok else ""))
    if not ok:
        failures.append(name)


def make_user(tag: str) -> tuple[str, str]:
    """Create a confirmed user via the admin API; return (email, access_token)."""
    email = f"verify-{tag}-{uuid.uuid4().hex[:8]}@example.com"
    password = "Verify-" + uuid.uuid4().hex[:12]
    r = httpx.post(
        f"{SUPABASE_URL}/auth/v1/admin/users",
        headers=admin_headers,
        json={"email": email, "password": password, "email_confirm": True},
        timeout=15,
    )
    r.raise_for_status()
    r = httpx.post(
        f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
        headers={"apikey": SECRET_KEY},
        json={"email": email, "password": password},
        timeout=15,
    )
    r.raise_for_status()
    return email, r.json()["access_token"]


def backend(token: str, method: str, path: str, **kw) -> httpx.Response:
    return httpx.request(method, API + path, headers={"Authorization": f"Bearer {token}"}, timeout=20, **kw)


def main():
    print("Creating two users in two organizations...")
    _, token_a = make_user("orga")
    _, token_b = make_user("orgb")

    for token, name in [(token_a, "Org Alpha"), (token_b, "Org Beta")]:
        r = backend(token, "POST", "/api/organizations/bootstrap", json={"organization_name": name})
        r.raise_for_status()

    role_a = backend(token_a, "POST", "/api/roles", json={"title": "Role A", "description": "JD A"}).json()
    role_b = backend(token_b, "POST", "/api/roles", json={"title": "Role B", "description": "JD B"}).json()

    print("\nBackend API isolation:")
    roles_seen_by_a = backend(token_a, "GET", "/api/roles").json()
    roles_seen_by_b = backend(token_b, "GET", "/api/roles").json()
    check("A sees only own roles", [r["id"] for r in roles_seen_by_a] == [role_a["id"]])
    check("B sees only own roles", [r["id"] for r in roles_seen_by_b] == [role_b["id"]])
    check("A cannot fetch B's role by id", backend(token_a, "GET", f"/api/roles/{role_b['id']}").status_code == 404)
    check("B cannot update A's role", backend(token_b, "PATCH", f"/api/roles/{role_a['id']}", json={"title": "hacked"}).status_code == 404)

    print("\nRLS isolation (direct PostgREST with user tokens):")
    def rest(token: str, query: str):
        r = httpx.get(
            f"{SUPABASE_URL}/rest/v1/{query}",
            headers={"apikey": SECRET_KEY, "Authorization": f"Bearer {token}"},
            timeout=15,
        )
        r.raise_for_status()
        return r.json()

    rows_a = rest(token_a, "roles?select=id")
    rows_b = rest(token_b, "roles?select=id")
    check("RLS: A's token returns only A's rows", [r["id"] for r in rows_a] == [role_a["id"]], str(rows_a))
    check("RLS: B's token returns only B's rows", [r["id"] for r in rows_b] == [role_b["id"]], str(rows_b))
    orgs_a = rest(token_a, "organizations?select=name")
    check("RLS: A sees only own organization", [o["name"] for o in orgs_a] == ["Org Alpha"], str(orgs_a))

    print()
    if failures:
        print(f"{len(failures)} check(s) FAILED")
        sys.exit(1)
    print("All Phase 1 isolation checks passed.")


if __name__ == "__main__":
    main()
