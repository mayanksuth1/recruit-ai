"""Admin dashboard verification: access control, activity logging, and the
metadata-only boundary.

Prereqs: migrations 0014-0015 applied; backend on 127.0.0.1:8000 started with
PLATFORM_ADMIN_USER_IDS set to the id of the ADMIN account created here
(pass it in via the ADMIN_EMAIL / ADMIN_PASSWORD / USER_EMAIL / USER_PASSWORD
environment variables, all for throwaway accounts).

Run:  python scripts/verify_admin.py
"""
import os
import sys
import uuid

import httpx
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "backend", ".env"))
SUPABASE_URL = os.environ["SUPABASE_URL"]
SECRET_KEY = os.environ["SUPABASE_SECRET_KEY"]
API = os.environ.get("API", "http://127.0.0.1:8000")
admin_h = {"apikey": SECRET_KEY, "Authorization": f"Bearer {SECRET_KEY}"}
failures = []

SECRET_CANDIDATE = f"Zelda-Private-{uuid.uuid4().hex[:6]}"
SECRET_EMAIL = f"{SECRET_CANDIDATE.lower()}@candidate.example"


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail and not ok else ""))
    if not ok:
        failures.append(name)


def token(email, pw):
    return httpx.post(f"{SUPABASE_URL}/auth/v1/token?grant_type=password", headers={"apikey": SECRET_KEY},
                      json={"email": email, "password": pw}, timeout=15).json()["access_token"]


def main():
    A = {"Authorization": f"Bearer {token(os.environ['ADMIN_EMAIL'], os.environ['ADMIN_PASSWORD'])}"}
    U = {"Authorization": f"Bearer {token(os.environ['USER_EMAIL'], os.environ['USER_PASSWORD'])}"}

    print("Access control:")
    for path in ("/api/admin/me", "/api/admin/overview", "/api/admin/workspaces", "/api/admin/activity",
                 "/api/admin/users", "/api/admin/signins", "/api/admin/alerts"):
        r = httpx.get(f"{API}{path}", headers=U, timeout=30)
        check(f"normal user gets 404 on {path}", r.status_code == 404, f"{r.status_code}")
    check("anonymous gets 401 on /api/admin/overview", httpx.get(f"{API}/api/admin/overview", timeout=30).status_code == 401)
    check("admin gets 200 on /api/admin/me", httpx.get(f"{API}/api/admin/me", headers=A, timeout=30).status_code == 200)

    print("\nActivity is recorded (normal user works in their own workspace):")
    httpx.post(f"{API}/api/organizations/bootstrap", headers=U, json={"organization_name": "Admin Verify Agency"},
               timeout=20).raise_for_status()
    org_id = httpx.get(f"{API}/api/organizations/me", headers=U, timeout=20).json()["id"]
    role = httpx.post(f"{API}/api/roles", headers=U, json={"title": "Secret Title QA", "description": "x"}, timeout=20).json()
    httpx.patch(f"{API}/api/roles/{role['id']}", headers=U, json={"status": "open"}, timeout=20)
    # A candidate with a recognisable name and email, straight into the DB.
    httpx.post(f"{SUPABASE_URL}/rest/v1/candidates", headers=admin_h, json={
        "organization_id": org_id, "role_id": role["id"], "full_name": SECRET_CANDIDATE,
        "email": SECRET_EMAIL, "phone": "+91 99999 00000", "source": "manual",
        "resume_text": f"{SECRET_CANDIDATE} resume body", "stage": "screening"}, timeout=20).raise_for_status()
    # A wrong password through the public auth proxy.
    httpx.post(f"{API}/supabase/auth/v1/token?grant_type=password", headers={"apikey": SECRET_KEY},
               json={"email": os.environ["USER_EMAIL"], "password": "definitely-wrong"}, timeout=20)

    feed = httpx.get(f"{API}/api/admin/activity?workspace_id={org_id}", headers=A, timeout=30).json()
    actions = [f["action"] for f in feed]
    check("role creation logged as a route template", "POST /api/roles" in actions, str(actions))
    check("role edit logged without the id", "PATCH /api/roles/{role_id}" in actions, str(actions))
    check("entries attributed to the user", all(f["user"] == os.environ["USER_EMAIL"] for f in feed if f["action"] == "POST /api/roles"))
    allfeed = httpx.get(f"{API}/api/admin/activity?limit=100", headers=A, timeout=30).json()
    check("failed sign-in recorded", any(f["action"] == "auth.failed_login"
                                         and f["meta"].get("email") == os.environ["USER_EMAIL"] for f in allfeed))

    print("\nWorkspace view shows counts, never candidate content:")
    detail = httpx.get(f"{API}/api/admin/workspaces/{org_id}", headers=A, timeout=30)
    body = detail.text
    w = detail.json()["workspace"]
    check("candidate counted", w["candidates"] == 1 and w["candidates_by_stage"].get("screening") == 1, str(w))
    check("role counted", w["roles_total"] == 1)
    everything = body + "".join(httpx.get(f"{API}{p}", headers=A, timeout=30).text for p in
                                ("/api/admin/overview", "/api/admin/workspaces", "/api/admin/activity?limit=1000",
                                 "/api/admin/users", "/api/admin/alerts"))
    check("candidate name appears nowhere in admin responses", SECRET_CANDIDATE not in everything)
    check("candidate email appears nowhere", SECRET_EMAIL not in everything)
    check("candidate phone appears nowhere", "99999 00000" not in everything)
    check("resume text appears nowhere", "resume body" not in everything)
    check("job title not exposed either", "Secret Title QA" not in everything)
    view = httpx.get(f"{API}/api/admin/activity?limit=20", headers=A, timeout=30).json()
    check("admin opening a workspace is itself logged",
          any(f["action"] == "admin.viewed_workspace" and f["meta"].get("workspace_id") == org_id for f in view))

    print("\nOverview, users, sign-ins, alerts:")
    ov = httpx.get(f"{API}/api/admin/overview", headers=A, timeout=30).json()
    check("overview has a 30-day series", len(ov["series"]) == 30 and ov["workspaces"] >= 1, str(ov)[:200])
    users = httpx.get(f"{API}/api/admin/users", headers=A, timeout=30).json()
    check("users list includes the workspace", any(u["email"] == os.environ["USER_EMAIL"]
                                                   and u["workspace"] == "Admin Verify Agency" for u in users))
    si = httpx.get(f"{API}/api/admin/signins", headers=A, timeout=30).json()
    check("sign-in history returned", any(s["action"] == "login" for s in si), str(si[:2]))
    al = httpx.get(f"{API}/api/admin/alerts", headers=A, timeout=30)
    check("alerts load", al.status_code == 200 and "dormant_signups" in al.json())
    legal = httpx.get(f"{API}/api/public/legal", timeout=30).json()
    check("public legal facts served", legal["activity_retention_days"] == 365)

    print("\nCleanup...")
    httpx.delete(f"{SUPABASE_URL}/rest/v1/organizations?id=eq.{org_id}", headers=admin_h, timeout=20)
    print()
    if failures:
        print(f"{len(failures)} check(s) FAILED")
        sys.exit(1)
    print("All admin checks passed.")


if __name__ == "__main__":
    main()
