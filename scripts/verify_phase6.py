"""Phase 6 verification: reporting reflects real data accurately.

Seeds a known funnel (10 sourced, 8 screened, 5 outreached, 3 interviewed,
2 offered, 1 closed) and asserts:
  - recruiter funnel counts + drop-off rates match exactly
  - per-role breakdown matches
  - client summary has identical numbers and ZERO candidate PII
  - weekly summary is stored (once — idempotent) and downloads as a valid PDF
  - scheduler auto-generates the weekly report

Prereqs: migrations 0001-0006 applied, backend on localhost:8000.
"""
import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from dotenv import load_dotenv

HERE = os.path.dirname(__file__)
load_dotenv(os.path.join(HERE, "..", "backend", ".env"))

SUPABASE_URL = os.environ["SUPABASE_URL"]
SECRET_KEY = os.environ["SUPABASE_SECRET_KEY"]
API = "http://localhost:8000"
admin = {"apikey": SECRET_KEY, "Authorization": f"Bearer {SECRET_KEY}", "Prefer": "return=representation"}

failures = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail and not ok else ""))
    if not ok:
        failures.append(name)


def main():
    email = f"verify6-{uuid.uuid4().hex[:8]}@example.com"
    password = "Verify-" + uuid.uuid4().hex[:12]
    httpx.post(f"{SUPABASE_URL}/auth/v1/admin/users", headers=admin,
               json={"email": email, "password": password, "email_confirm": True}, timeout=15).raise_for_status()
    tok = httpx.post(f"{SUPABASE_URL}/auth/v1/token?grant_type=password", headers={"apikey": SECRET_KEY},
                     json={"email": email, "password": password}, timeout=15).json()["access_token"]
    H = {"Authorization": f"Bearer {tok}"}
    httpx.post(f"{API}/api/organizations/bootstrap", headers=H,
               json={"organization_name": "Phase6 Verify Org"}, timeout=20).raise_for_status()
    org_id = httpx.get(f"{API}/api/organizations/me", headers=H, timeout=20).json()["id"]

    role = httpx.post(f"{API}/api/roles", headers=H,
                      json={"title": "Reporting Role", "description": "JD"}, timeout=20).json()

    print("Seeding a known funnel (10/8/5/3/2/1)...")
    cand_ids = []
    for i in range(10):
        stage = "closed" if i == 0 else ("offer" if i == 1 else "screening")
        c = httpx.post(f"{SUPABASE_URL}/rest/v1/candidates", headers=admin, json={
            "organization_id": org_id, "role_id": role["id"],
            "full_name": f"Funnel Person{i}", "email": f"funnel{i}@example.com",
            "source": "manual", "stage": stage,
            "shortlist_status": "approved" if i < 5 else "pending",
        }, timeout=20).json()[0]
        cand_ids.append(c["id"])
    # 8 screened (have scores)
    for i in range(8):
        httpx.post(f"{SUPABASE_URL}/rest/v1/scores", headers=admin, json={
            "organization_id": org_id, "candidate_id": cand_ids[i], "role_id": role["id"],
            "overall_score": 50 + i * 5, "rationale": "seed",
        }, timeout=20).raise_for_status()
    # 5 outreached (sent outreach messages)
    for i in range(5):
        httpx.post(f"{SUPABASE_URL}/rest/v1/messages", headers=admin, json={
            "organization_id": org_id, "candidate_id": cand_ids[i], "role_id": role["id"],
            "kind": "outreach", "to_email": f"funnel{i}@example.com",
            "subject": "s", "body": "b", "status": "sent",
            "sent_at": datetime.now(timezone.utc).isoformat(),
        }, timeout=20).raise_for_status()
    # 3 interviewed
    start = datetime.now(timezone.utc) + timedelta(days=2)
    for i in range(3):
        httpx.post(f"{SUPABASE_URL}/rest/v1/interviews", headers=admin, json={
            "organization_id": org_id, "candidate_id": cand_ids[i], "role_id": role["id"],
            "status": "scheduled",
            "scheduled_start": start.isoformat(),
            "scheduled_end": (start + timedelta(minutes=45)).isoformat(),
        }, timeout=20).raise_for_status()

    expected = {"sourced": 10, "screened": 8, "outreached": 5, "interviewed": 3, "offered": 2, "closed": 1}
    expected_drop = {"screened": 20.0, "outreached": 37.5, "interviewed": 40.0, "offered": 33.3, "closed": 50.0}

    print("\nRecruiter funnel:")
    data = httpx.get(f"{API}/api/reports/funnel", headers=H, timeout=30).json()
    got = {f["stage"]: f["count"] for f in data["funnel"]}
    check("funnel counts exact", got == expected, str(got))
    drops = {f["stage"]: f["drop_off_pct"] for f in data["funnel"] if f["drop_off_pct"] is not None}
    check("drop-off rates exact", drops == expected_drop, str(drops))
    check("avg score correct (67.5)", data["totals"]["avg_score"] == 67.5, str(data["totals"]))
    check("upcoming interviews visible in recruiter view",
          len(data.get("upcoming_interviews", [])) == 3, str(len(data.get("upcoming_interviews", []))))
    row = next((r for r in data["per_role"] if r["role_title"] == "Reporting Role"), None)
    check("per-role breakdown matches",
          row is not None and all(row[k] == v for k, v in expected.items()), str(row))

    print("\nClient summary (no PII):")
    client = httpx.get(f"{API}/api/reports/client-summary", headers=H, timeout=30).json()
    cgot = {f["stage"]: f["count"] for f in client["funnel"]}
    check("client numbers identical", cgot == expected, str(cgot))
    blob = json.dumps(client)
    leaked = [s for s in (["Funnel Person" + str(i) for i in range(10)] +
                          [f"funnel{i}@example.com" for i in range(10)]) if s in blob]
    check("zero candidate names/emails in client payload", not leaked, str(leaked))
    check("role titles allowed (needed for context)", "Reporting Role" in blob)

    print("\nWeekly summary + PDF:")
    r = httpx.post(f"{API}/api/reports/generate", headers=H, timeout=30).json()
    check("weekly summary created", r["created"] is True and r["latest"], str(r)[:150])
    r2 = httpx.post(f"{API}/api/reports/generate", headers=H, timeout=30).json()
    check("idempotent per week (no duplicate)", r2["created"] is False)
    report_id = r["latest"]["id"]
    pdf = httpx.get(f"{API}/api/reports/{report_id}/pdf", headers=H, timeout=30)
    check("PDF downloads", pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf",
          f"{pdf.status_code} {pdf.headers.get('content-type')}")
    check("PDF is valid and non-trivial", pdf.content[:5] == b"%PDF-" and len(pdf.content) > 1500,
          f"magic={pdf.content[:5]}, size={len(pdf.content)}")

    print("\nScheduler auto-generation:")
    httpx.delete(f"{SUPABASE_URL}/rest/v1/reports?organization_id=eq.{org_id}",
                 headers=admin, timeout=20)
    checks = httpx.post(f"{API}/api/scheduler/run-checks", headers=H, json={}, timeout=120).json()
    check("weekly report auto-generated by scheduler", checks.get("weekly_reports", 0) >= 1, str(checks))
    reports = httpx.get(f"{API}/api/reports", headers=H, timeout=20).json()
    check("stored report visible in list", len(reports) == 1, str(len(reports)))

    print("\nCleanup...")
    httpx.delete(f"{SUPABASE_URL}/rest/v1/organizations?id=eq.{org_id}", headers=admin, timeout=20)
    users = httpx.get(f"{SUPABASE_URL}/auth/v1/admin/users?per_page=100", headers=admin, timeout=20).json()["users"]
    for u in users:
        if u.get("email") == email:
            httpx.delete(f"{SUPABASE_URL}/auth/v1/admin/users/{u['id']}", headers=admin, timeout=20)

    print()
    if failures:
        print(f"{len(failures)} check(s) FAILED")
        sys.exit(1)
    print("All Phase 6 checks passed.")


if __name__ == "__main__":
    main()
