"""Phase 2 verification: CSV import of 20 mock candidates -> pool-vs-JD match
scoring produces sensible rankings; dedup on re-import; Boolean search; bulk
shortlist.

Prereqs: migrations 0001+0002 applied, backend running on localhost:8000.
Run:  backend\\.venv\\Scripts\\python scripts\\verify_phase2.py
"""
import os
import sys
import uuid

import httpx
from dotenv import load_dotenv

HERE = os.path.dirname(__file__)
load_dotenv(os.path.join(HERE, "..", "backend", ".env"))

SUPABASE_URL = os.environ["SUPABASE_URL"]
SECRET_KEY = os.environ["SUPABASE_SECRET_KEY"]
API = "http://localhost:8000"
admin = {"apikey": SECRET_KEY, "Authorization": f"Bearer {SECRET_KEY}"}

JD = (
    "Senior Backend Engineer: 5+ years building production backend services in "
    "Python (FastAPI or Django), strong PostgreSQL, AWS, and experience designing "
    "multi-tenant SaaS systems. Nice to have: React, Kubernetes."
)
STRONG = {f"{n}@example.com" for n in (
    "arjun.mehta", "sneha.iyer", "rohan.desai", "kavita.reddy", "nikhil.banerjee", "meera.krishnan")}
POOR = {f"{n}@example.com" for n in (
    "karan.chopra", "lakshmi.menon", "rajesh.khanna", "fatima.ansari", "deepak.rawat", "ishaan.bhatt")}

failures = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail and not ok else ""))
    if not ok:
        failures.append(name)


def main():
    email = f"verify2-{uuid.uuid4().hex[:8]}@example.com"
    password = "Verify-" + uuid.uuid4().hex[:12]
    httpx.post(f"{SUPABASE_URL}/auth/v1/admin/users", headers=admin,
               json={"email": email, "password": password, "email_confirm": True}, timeout=15).raise_for_status()
    tok = httpx.post(f"{SUPABASE_URL}/auth/v1/token?grant_type=password", headers={"apikey": SECRET_KEY},
                     json={"email": email, "password": password}, timeout=15).json()["access_token"]
    H = {"Authorization": f"Bearer {tok}"}
    httpx.post(f"{API}/api/organizations/bootstrap", headers=H,
               json={"organization_name": "Phase2 Verify Org"}, timeout=20).raise_for_status()

    csv_bytes = open(os.path.join(HERE, "mock_candidates_20.csv"), "rb").read()

    print("CSV import:")
    r = httpx.post(f"{API}/api/talent-pool/import", headers=H,
                   files={"file": ("mock.csv", csv_bytes, "text/csv")}, timeout=60).json()
    check("20 candidates inserted", r.get("inserted") == 20, str(r))

    r2 = httpx.post(f"{API}/api/talent-pool/import", headers=H,
                    files={"file": ("mock.csv", csv_bytes, "text/csv")}, timeout=60).json()
    check("re-import creates no duplicates", r2.get("inserted") == 0 and r2.get("updated") == 20, str(r2))

    pool = httpx.get(f"{API}/api/talent-pool", headers=H, timeout=20).json()
    check("pool holds exactly 20", len(pool) == 20, str(len(pool)))

    print("\nJD-to-pool match scoring (Gemini, 20 profiles):")
    role = httpx.post(f"{API}/api/roles", headers=H,
                      json={"title": "Senior Backend Engineer", "description": JD}, timeout=20).json()
    r = httpx.post(f"{API}/api/roles/{role['id']}/match-pool", headers=H, json={}, timeout=600).json()
    check("all 20 scored and added", r.get("matched") == 20, str(r))

    cands = httpx.get(f"{API}/api/roles/{role['id']}/candidates", headers=H, timeout=20).json()
    scored = [(c["email"], c["scores"][0]["overall_score"], c) for c in cands if c.get("scores")]
    scored.sort(key=lambda x: -x[1])
    print("\n  Ranked results:")
    for em, sc, c in scored:
        tag = "STRONG" if em in STRONG else ("POOR" if em in POOR else "mid")
        print(f"    {sc:5.0f}  {c['full_name']:<20} {tag}")

    strong_scores = [sc for em, sc, _ in scored if em in STRONG]
    poor_scores = [sc for em, sc, _ in scored if em in POOR]
    check("every strong candidate outscores every poor one",
          min(strong_scores) > max(poor_scores),
          f"min(strong)={min(strong_scores)}, max(poor)={max(poor_scores)}")
    check("poor candidates score below 40", max(poor_scores) < 40, str(poor_scores))
    check("strong candidates score above 60", min(strong_scores) > 60, str(strong_scores))

    print("\nBoolean search generator:")
    b = httpx.post(f"{API}/api/roles/{role['id']}/boolean-search", headers=H, timeout=120).json()
    check("linkedin string generated", bool(b.get("linkedin", "").strip()))
    check("google x-ray string generated", "linkedin.com/in" in b.get("google_xray", ""))
    print(f"    linkedin: {b.get('linkedin', '')[:120]}")
    print(f"    x-ray:    {b.get('google_xray', '')[:120]}")

    print("\nBulk shortlist:")
    top5 = [c["id"] for _, _, c in scored[:5]]
    r = httpx.patch(f"{API}/api/candidates/bulk-shortlist", headers=H,
                    json={"candidate_ids": top5, "shortlist_status": "approved"}, timeout=20).json()
    check("bulk-approve top 5", r.get("updated") == 5, str(r))

    print("\nCleanup...")
    org_id = httpx.get(f"{API}/api/organizations/me", headers=H, timeout=20).json()["id"]
    httpx.delete(f"{SUPABASE_URL}/rest/v1/organizations?id=eq.{org_id}", headers=admin, timeout=20)
    users = httpx.get(f"{SUPABASE_URL}/auth/v1/admin/users?per_page=100", headers=admin, timeout=20).json()["users"]
    for u in users:
        if u.get("email") == email:
            httpx.delete(f"{SUPABASE_URL}/auth/v1/admin/users/{u['id']}", headers=admin, timeout=20)

    print()
    if failures:
        print(f"{len(failures)} check(s) FAILED")
        sys.exit(1)
    print("All Phase 2 checks passed.")


if __name__ == "__main__":
    main()
