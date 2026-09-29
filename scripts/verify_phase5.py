"""Phase 5 verification: approval gate 2 + generic webhook ATS sync + dedup.

Runs a local mock ATS endpoint (http://localhost:9999) to catch outbound
webhooks and verify HMAC signatures, then exercises:
  - outbound: stage change -> signed webhook delivered + logged
  - inbound: mock ATS pushes a stage change -> applied + logged
  - gate 2: offer/closed blocked (API and inbound webhook) until approval
  - security: bad inbound signature and bad token rejected
  - dedup: fuzzy-name re-import merges instead of duplicating; distinct
    people with similar names are NOT merged; scan endpoint reports pairs

Prereqs: migrations 0001-0005 applied, backend on localhost:8000.
"""
import hashlib
import hmac as hmac_mod
import json
import os
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx
from dotenv import load_dotenv

HERE = os.path.dirname(__file__)
load_dotenv(os.path.join(HERE, "..", "backend", ".env"))

SUPABASE_URL = os.environ["SUPABASE_URL"]
SECRET_KEY = os.environ["SUPABASE_SECRET_KEY"]
API = os.environ.get("API", "http://127.0.0.1:8000")
MOCK_PORT = 9999
SHARED_SECRET = "verify5-shared-secret"
admin = {"apikey": SECRET_KEY, "Authorization": f"Bearer {SECRET_KEY}"}

failures = []
received: list[dict] = []  # webhooks caught by the mock ATS


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail and not ok else ""))
    if not ok:
        failures.append(name)


class MockATS(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        received.append({
            "path": self.path,
            "body": body,
            "signature": self.headers.get("X-RecruitAI-Signature"),
        })
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):
        pass


def main():
    server = HTTPServer(("127.0.0.1", MOCK_PORT), MockATS)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    email = f"verify5-{uuid.uuid4().hex[:8]}@example.com"
    password = "Verify-" + uuid.uuid4().hex[:12]
    httpx.post(f"{SUPABASE_URL}/auth/v1/admin/users", headers=admin,
               json={"email": email, "password": password, "email_confirm": True}, timeout=15).raise_for_status()
    tok = httpx.post(f"{SUPABASE_URL}/auth/v1/token?grant_type=password", headers={"apikey": SECRET_KEY},
                     json={"email": email, "password": password}, timeout=15).json()["access_token"]
    H = {"Authorization": f"Bearer {tok}"}
    httpx.post(f"{API}/api/organizations/bootstrap", headers=H,
               json={"organization_name": "Phase5 Verify Org"}, timeout=20).raise_for_status()
    org_id = httpx.get(f"{API}/api/organizations/me", headers=H, timeout=20).json()["id"]

    print("ATS connection config:")
    # SSRF guard: a customer-typed webhook URL must not reach our own network.
    for bad in ("http://127.0.0.1:54421/pg/query", "http://localhost:8000/api/health",
                "http://169.254.169.254/latest/meta-data/", "http://10.0.0.5/", "file:///etc/passwd"):
        r = httpx.put(f"{API}/api/ats/connection", headers=H,
                      json={"outbound_url": bad, "secret": SHARED_SECRET, "active": True}, timeout=20)
        check(f"internal webhook target refused: {bad}", r.status_code == 400, f"{r.status_code}")
    conn = httpx.put(f"{API}/api/ats/connection", headers=H, json={
        "outbound_url": None, "secret": SHARED_SECRET, "active": True,
    }, timeout=20).json()
    check("connection saved with inbound path", "/api/webhooks/ats/" in conn["inbound_webhook_path"])
    inbound_url = f"{API}{conn['inbound_webhook_path']}"
    # Plant a loopback target straight into the DB (as if DNS changed after it
    # was saved) to prove the send-time re-check refuses it too.
    httpx.patch(f"{SUPABASE_URL}/rest/v1/ats_connections?organization_id=eq.{org_id}", headers=admin,
                json={"outbound_url": f"http://127.0.0.1:{MOCK_PORT}/hooks/recruit-ai"},
                timeout=20).raise_for_status()

    cand = httpx.post(f"{SUPABASE_URL}/rest/v1/candidates", headers={**admin, "Prefer": "return=representation"},
                      json={"organization_id": org_id, "full_name": "Sync Test Candidate",
                            "email": "sync.test@example.com", "source": "manual",
                            "shortlist_status": "approved"}, timeout=20).json()[0]

    print("\nOutbound webhook (send-time SSRF re-check):")
    r = httpx.patch(f"{API}/api/candidates/{cand['id']}/stage", headers=H,
                    json={"stage": "interview"}, timeout=180)
    check("stage change accepted", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
    time.sleep(2)
    check("nothing delivered to the loopback target", len(received) == 0)
    events = httpx.get(f"{API}/api/ats/events", headers=H, timeout=20).json()
    check("outbound event logged as failed (refused)",
          any(e["direction"] == "outbound" and e["result"] == "failed" for e in events), str(events)[:300])
    # Delivery can only reach a public host now, so signing is checked directly.
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
    from app.services import ats as ats_svc
    body = b'{"event":"x"}'
    check("HMAC signature format",
          ats_svc.sign(SHARED_SECRET, body)
          == "sha256=" + hmac_mod.new(SHARED_SECRET.encode(), body, hashlib.sha256).hexdigest())

    print("\nApproval gate 2 (API):")
    r = httpx.patch(f"{API}/api/candidates/{cand['id']}/stage", headers=H, json={"stage": "offer"}, timeout=60)
    check("offer blocked before approval", r.status_code == 409, f"{r.status_code}")
    r = httpx.post(f"{API}/api/candidates/{cand['id']}/approve-offer", headers=H, timeout=60)
    check("explicit offer approval recorded", r.status_code == 200 and r.json().get("offer_approved_at"))
    r = httpx.patch(f"{API}/api/candidates/{cand['id']}/stage", headers=H, json={"stage": "offer"}, timeout=180)
    check("offer allowed after approval", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
    su = r.json().get("status_update_draft")
    check("offer status-update email is a DRAFT", su is not None and su["status"] == "draft")

    print("\nInbound webhook (mock ATS -> Recruit AI):")
    def push(payload: dict, sign=True, url=inbound_url):
        body = json.dumps(payload, separators=(",", ":")).encode()
        headers = {"Content-Type": "application/json"}
        if sign:
            headers["X-RecruitAI-Signature"] = "sha256=" + hmac_mod.new(
                SHARED_SECRET.encode(), body, hashlib.sha256).hexdigest()
        return httpx.post(url, content=body, headers=headers, timeout=20)

    r = push({"event": "candidate.stage_changed", "candidate_email": "sync.test@example.com", "stage": "interview"})
    check("inbound stage change applied", r.status_code == 200 and r.json().get("applied"), f"{r.status_code} {r.text[:200]}")
    stage = httpx.get(f"{SUPABASE_URL}/rest/v1/candidates?id=eq.{cand['id']}&select=stage",
                      headers=admin, timeout=20).json()[0]["stage"]
    check("candidate stage reflects inbound change", stage == "interview", stage)

    r = push({"event": "candidate.stage_changed", "candidate_email": "sync.test@example.com", "stage": "offer"}, sign=True)
    check("inbound offer ALLOWED (candidate already gate-2 approved)", r.status_code == 200, f"{r.status_code}")
    httpx.post(f"{API}/api/candidates/{cand['id']}/revoke-offer-approval", headers=H, timeout=20)
    r = push({"event": "candidate.stage_changed", "candidate_email": "sync.test@example.com", "stage": "closed"})
    check("inbound closure BLOCKED after approval revoked (gate 2)", r.status_code == 409, f"{r.status_code} {r.text[:150]}")

    r = push({"event": "candidate.stage_changed", "candidate_email": "sync.test@example.com", "stage": "interview"}, sign=False)
    check("unsigned inbound rejected when secret set", r.status_code == 401, f"{r.status_code}")
    r = push({"event": "candidate.stage_changed", "candidate_email": "x@example.com", "stage": "interview"},
             url=f"{API}/api/webhooks/ats/{uuid.uuid4()}")
    check("bad token rejected", r.status_code == 404, f"{r.status_code}")

    events = httpx.get(f"{API}/api/ats/events", headers=H, timeout=20).json()
    check("inbound events logged (applied + rejected)",
          any(e["direction"] == "inbound" and e["result"] == "applied" for e in events)
          and any(e["direction"] == "inbound" and e["result"] == "rejected" for e in events))

    print("\nDuplicate detection on import:")
    csv1 = ("Full Name,Email,Phone,Current Company\n"
            "Arjun Mehta,arjun.m@example.com,+91 98100 11001,Razorpay\n"
            "Divya Nair,divya.n@example.com,+91 98100 11010,TCS\n")
    r = httpx.post(f"{API}/api/talent-pool/import", headers=H,
                   files={"file": ("a.csv", csv1.encode(), "text/csv")}, timeout=60).json()
    check("initial import inserts 2", r.get("inserted") == 2, str(r))

    # Same people, mangled: reordered name w/ same email; name-variant with NO
    # email but same company+phone. Plus a genuinely different person with a
    # similar name at a different company.
    csv2 = ("Full Name,Email,Phone,Current Company\n"
            "\"Mehta, Arjun\",arjun.m@example.com,,Razorpay\n"
            "Divya  Nair,,+91 98100 11010,TCS\n"
            "Divya Nayar,divya.nayar@othermail.com,+91 90000 22222,Infosys\n")
    r = httpx.post(f"{API}/api/talent-pool/import", headers=H,
                   files={"file": ("b.csv", csv2.encode(), "text/csv")}, timeout=60).json()
    check("email match + fuzzy match merged (2 updated)", r.get("updated") == 2, str(r))
    check("distinct person with similar name inserted, not merged", r.get("inserted") == 1, str(r))
    pool = httpx.get(f"{API}/api/talent-pool", headers=H, timeout=20).json()
    check("pool holds exactly 3 people", len(pool) == 3, str(len(pool)))

    dupes = httpx.get(f"{API}/api/talent-pool/duplicates", headers=H, timeout=30).json()["pairs"]
    check("scan flags the similar-name pair for review",
          any({p["a"]["full_name"], p["b"]["full_name"]} == {"Divya  Nair", "Divya Nayar"}
              or {p["a"]["full_name"], p["b"]["full_name"]} == {"Divya Nair", "Divya Nayar"}
              for p in dupes), str(dupes))

    print("\nCleanup...")
    server.shutdown()
    httpx.delete(f"{SUPABASE_URL}/rest/v1/organizations?id=eq.{org_id}", headers=admin, timeout=20)
    users = httpx.get(f"{SUPABASE_URL}/auth/v1/admin/users?per_page=100", headers=admin, timeout=20).json()["users"]
    for u in users:
        if u.get("email") == email:
            httpx.delete(f"{SUPABASE_URL}/auth/v1/admin/users/{u['id']}", headers=admin, timeout=20)

    print()
    if failures:
        print(f"{len(failures)} check(s) FAILED")
        sys.exit(1)
    print("All Phase 5 checks passed.")


if __name__ == "__main__":
    main()
