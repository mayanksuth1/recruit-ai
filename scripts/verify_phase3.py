"""Phase 3 verification: approval gate 1 + reviewed-before-send engagement.

Checks:
  1. Outreach cannot be drafted for a non-approved candidate (gate 1).
  2. Approving unlocks drafting; the draft is NOT sent.
  3. Draft can be edited (simulates UI edit).
  4. Explicit send delivers a real email via Resend to TEST_INBOX.
  5. Double-send is rejected.
  6. Stage change auto-DRAFTS a status update (never sends).
  7. Back-dated sent outreach with no response yields a follow-up draft.
  8. Discarded drafts cannot be sent.

Prereqs: migrations 0001-0003 applied, backend on localhost:8000.
NOTE: Resend sandbox (no verified domain) only delivers to the Resend
account owner's email — set TEST_INBOX accordingly.
"""
import os
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from dotenv import load_dotenv

HERE = os.path.dirname(__file__)
load_dotenv(os.path.join(HERE, "..", "backend", ".env"))

SUPABASE_URL = os.environ["SUPABASE_URL"]
SECRET_KEY = os.environ["SUPABASE_SECRET_KEY"]
API = "http://localhost:8000"
TEST_INBOX = os.environ.get("TEST_INBOX", "mayanksuth1@gmail.com")
admin = {"apikey": SECRET_KEY, "Authorization": f"Bearer {SECRET_KEY}"}

failures = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail and not ok else ""))
    if not ok:
        failures.append(name)


def main():
    email = f"verify3-{uuid.uuid4().hex[:8]}@example.com"
    password = "Verify-" + uuid.uuid4().hex[:12]
    httpx.post(f"{SUPABASE_URL}/auth/v1/admin/users", headers=admin,
               json={"email": email, "password": password, "email_confirm": True}, timeout=15).raise_for_status()
    tok = httpx.post(f"{SUPABASE_URL}/auth/v1/token?grant_type=password", headers={"apikey": SECRET_KEY},
                     json={"email": email, "password": password}, timeout=15).json()["access_token"]
    H = {"Authorization": f"Bearer {tok}"}
    httpx.post(f"{API}/api/organizations/bootstrap", headers=H,
               json={"organization_name": "Phase3 Verify Org"}, timeout=20).raise_for_status()
    org_id = httpx.get(f"{API}/api/organizations/me", headers=H, timeout=20).json()["id"]

    role = httpx.post(f"{API}/api/roles", headers=H, json={
        "title": "Senior Backend Engineer",
        "description": "5+ years Python, FastAPI, PostgreSQL, AWS; multi-tenant SaaS experience.",
    }, timeout=20).json()

    # Create a mock candidate directly (service client), pending approval.
    cand = httpx.post(f"{SUPABASE_URL}/rest/v1/candidates", headers={**admin, "Prefer": "return=representation"},
                      json={
                          "organization_id": org_id, "role_id": role["id"],
                          "full_name": "Priya Sharma", "email": TEST_INBOX,
                          "resume_text": "Senior Software Engineer at Flipkart. 9 years Python/FastAPI, "
                                         "PostgreSQL, AWS. Built a multi-tenant billing platform.",
                          "source": "manual",
                      }, timeout=20).json()[0]

    print("Approval gate 1:")
    r = httpx.post(f"{API}/api/candidates/{cand['id']}/draft-outreach", headers=H, timeout=120)
    check("drafting blocked while not approved", r.status_code == 409, f"{r.status_code} {r.text[:100]}")

    httpx.patch(f"{API}/api/candidates/{cand['id']}/shortlist", headers=H,
                json={"shortlist_status": "approved"}, timeout=20).raise_for_status()
    r = httpx.post(f"{API}/api/candidates/{cand['id']}/draft-outreach", headers=H, timeout=180)
    check("drafting allowed after approval", r.status_code == 201, f"{r.status_code} {r.text[:200]}")
    draft = r.json()
    check("draft created as draft (not sent)", draft["status"] == "draft")
    check("draft personalized (mentions candidate context)",
          any(w in draft["body"] for w in ("Flipkart", "multi-tenant", "FastAPI", "Priya")),
          draft["body"][:200])

    print("\nReview and edit:")
    edited_subject = f"[edited] {draft['subject']}"
    r = httpx.patch(f"{API}/api/messages/{draft['id']}", headers=H,
                    json={"subject": edited_subject}, timeout=20)
    check("draft editable", r.status_code == 200 and r.json()["subject"] == edited_subject)

    print("\nExplicit human send:")
    r = httpx.post(f"{API}/api/messages/{draft['id']}/send", headers=H, timeout=60)
    check("send succeeds", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
    sent = r.json()
    check("provider id recorded", bool(sent.get("provider_id")))
    r = httpx.post(f"{API}/api/messages/{draft['id']}/send", headers=H, timeout=20)
    check("double-send rejected", r.status_code == 409)

    delivered = None
    for _ in range(10):
        time.sleep(3)
        d = httpx.get(f"{API}/api/messages/{draft['id']}/delivery", headers=H, timeout=30).json()
        delivered = d.get("provider_status")
        if delivered in ("delivered", "bounced", "complained", "unknown_restricted_key"):
            break
    if delivered == "unknown_restricted_key":
        print(f"  NOTE  Resend key is send-only; cannot read delivery status. "
              f"Send was accepted by Resend — confirm arrival by checking {TEST_INBOX}.")
    else:
        check(f"Resend delivery status reaches 'delivered' (to {TEST_INBOX})",
              delivered == "delivered", str(delivered))

    print("\nStage-change status update (draft only):")
    r = httpx.patch(f"{API}/api/candidates/{cand['id']}/stage", headers=H,
                    json={"stage": "interview"}, timeout=180).json()
    su = r.get("status_update_draft")
    check("status-update draft created", su is not None and su["kind"] == "status_update")
    check("status-update is NOT auto-sent", su is not None and su["status"] == "draft")
    sent_now = httpx.get(f"{API}/api/messages?status=sent", headers=H, timeout=20).json()
    check("exactly one message actually sent so far", len(sent_now) == 1, str(len(sent_now)))

    print("\nFollow-up sequence:")
    backdate = (datetime.now(timezone.utc) - timedelta(days=6)).isoformat()
    httpx.patch(f"{SUPABASE_URL}/rest/v1/messages?id=eq.{draft['id']}", headers=admin,
                json={"sent_at": backdate}, timeout=20)
    r = httpx.post(f"{API}/api/engagement/follow-ups", headers=H, json={"days": 4}, timeout=180).json()
    check("follow-up drafted for unanswered outreach", r.get("drafted") == 1, str(r))
    fu = r["messages"][0] if r.get("messages") else None
    check("follow-up is a draft (not sent)", fu is not None and fu["status"] == "draft")
    r2 = httpx.post(f"{API}/api/engagement/follow-ups", headers=H, json={"days": 4}, timeout=60).json()
    check("no duplicate follow-up on re-run", r2.get("drafted") == 0, str(r2))

    print("\nDiscard safety:")
    if fu:
        httpx.post(f"{API}/api/messages/{fu['id']}/discard", headers=H, timeout=20)
        r = httpx.post(f"{API}/api/messages/{fu['id']}/send", headers=H, timeout=20)
        check("discarded draft cannot be sent", r.status_code == 409)

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
    print(f"All Phase 3 checks passed. Check {TEST_INBOX} for the outreach email.")


if __name__ == "__main__":
    main()
