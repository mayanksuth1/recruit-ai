"""Phase 4 verification: real end-to-end interview scheduling.

PREREQ: a recruiter must have connected Google Calendar in the app
(Settings -> Connect Google Calendar). The script uses that connection.

What it does (all against real Google Calendar + Resend):
  1. Creates a test candidate (email = TEST_INBOX) in the connected user's org.
  2. Proposes interview slots from the recruiter's real free/busy.
  3. Simulates the candidate picking a slot via the public link
     -> creates a REAL calendar event with Meet link; Google emails the invite.
  4. Confirms the event exists on the recruiter's Google Calendar.
  5. Backdates/forward-dates the interview to prove the 24h reminder draft
     and the 48h feedback nudge both fire.
  6. Cleans up DB rows; the calendar event is CANCELLED at the end (the
     invite + cancellation emails in the inbox are the human-visible proof).

Run:  backend\\.venv\\Scripts\\python scripts\\verify_phase4.py
"""
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
# Candidate invitee: a different inbox than the calendar owner, so the
# Google invite email actually arrives somewhere visible.
CANDIDATE_INBOX = os.environ.get("CANDIDATE_INBOX", "jambadmayank@gmail.com")
# Nudge recipient: must be the Resend account owner (sandbox restriction).
NUDGE_INBOX = os.environ.get("NUDGE_INBOX", "mayankdigikit@gmail.com")
admin = {"apikey": SECRET_KEY, "Authorization": f"Bearer {SECRET_KEY}"}

failures = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail and not ok else ""))
    if not ok:
        failures.append(name)


def token_for_user(email: str) -> str:
    """Mint a session for an existing user via admin magiclink + verify."""
    r = httpx.post(f"{SUPABASE_URL}/auth/v1/admin/generate_link", headers=admin,
                   json={"type": "magiclink", "email": email}, timeout=20)
    r.raise_for_status()
    data = r.json()
    token_hash = (data.get("properties") or data).get("hashed_token")
    if not token_hash:
        raise RuntimeError(f"generate_link returned no hashed_token: {list(data.keys())}")
    r = httpx.post(f"{SUPABASE_URL}/auth/v1/verify", headers={"apikey": SECRET_KEY},
                   json={"type": "magiclink", "token_hash": token_hash}, timeout=20)
    r.raise_for_status()
    return r.json()["access_token"]


def main():
    conns = httpx.get(f"{SUPABASE_URL}/rest/v1/calendar_connections?select=*", headers=admin, timeout=20).json()
    if not conns:
        print("No calendar connection found. Open the app -> Settings -> Connect Google Calendar, then re-run.")
        sys.exit(2)
    conn = conns[0]
    org_id, user_id = conn["organization_id"], conn["user_id"]
    user = httpx.get(f"{SUPABASE_URL}/auth/v1/admin/users/{user_id}", headers=admin, timeout=20).json()
    print(f"Using connection: {conn.get('google_email')} (app user {user.get('email')})\n")
    tok = token_for_user(user["email"])
    H = {"Authorization": f"Bearer {tok}"}

    cand = httpx.post(f"{SUPABASE_URL}/rest/v1/candidates", headers={**admin, "Prefer": "return=representation"},
                      json={"organization_id": org_id, "full_name": "Verify4 Candidate",
                            "email": CANDIDATE_INBOX, "source": "manual",
                            "shortlist_status": "approved"}, timeout=20).json()[0]

    print("Slot proposal from real free/busy:")
    r = httpx.post(f"{API}/api/candidates/{cand['id']}/interviews/propose", headers=H,
                   json={"duration_minutes": 30, "days_ahead": 3, "slots_wanted": 4}, timeout=60)
    check("propose succeeds", r.status_code == 201, f"{r.status_code} {r.text[:300]}")
    if r.status_code != 201:
        _cleanup(cand["id"])
        sys.exit(1)
    prop = r.json()
    check("slots computed", len(prop["slots"]) >= 1, str(len(prop.get("slots", []))))
    check("scheduling-link email drafted (not sent)", prop["draft"]["status"] == "draft")
    check("link uses public token", prop["interview"]["public_token"] in prop["link"])

    token = prop["interview"]["public_token"]
    print("\nCandidate books via public link:")
    pub = httpx.get(f"{API}/api/public/schedule/{token}", timeout=30).json()
    check("public page shows slots without auth", len(pub.get("slots", [])) >= 1)
    slot = pub["slots"][0]
    r = httpx.post(f"{API}/api/public/schedule/{token}", json={"start": slot["start"]}, timeout=60)
    check("slot selection creates event", r.status_code == 200, f"{r.status_code} {r.text[:300]}")
    booked = r.json() if r.status_code == 200 else {}
    check("meet link returned", bool(booked.get("meet_link")), str(booked))

    iv = httpx.get(f"{SUPABASE_URL}/rest/v1/interviews?candidate_id=eq.{cand['id']}&select=*",
                   headers=admin, timeout=20).json()[0]
    check("interview marked scheduled", iv["status"] == "scheduled")

    print("\nEvent really exists on Google Calendar:")
    conn_fresh = httpx.get(f"{SUPABASE_URL}/rest/v1/calendar_connections?user_id=eq.{user_id}&select=*",
                           headers=admin, timeout=20).json()[0]
    ev = httpx.get(f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{iv['google_event_id']}",
                   headers={"Authorization": f"Bearer {conn_fresh['access_token']}"}, timeout=20)
    check("event fetched from Google", ev.status_code == 200, f"{ev.status_code}")
    if ev.status_code == 200:
        attendees = [a["email"] for a in ev.json().get("attendees", [])]
        check(f"candidate ({CANDIDATE_INBOX}) invited", CANDIDATE_INBOX in attendees, str(attendees))

    print("\n24h reminder (draft only):")
    soon = datetime.now(timezone.utc) + timedelta(hours=2)
    httpx.patch(f"{SUPABASE_URL}/rest/v1/interviews?id=eq.{iv['id']}", headers=admin,
                json={"scheduled_start": soon.isoformat(),
                      "scheduled_end": (soon + timedelta(minutes=30)).isoformat()}, timeout=20)
    checks = httpx.post(f"{API}/api/scheduler/run-checks", headers=H, json={}, timeout=60).json()
    check("reminder drafted by checker", checks.get("reminders_drafted", 0) >= 1, str(checks))
    msgs = httpx.get(
        f"{SUPABASE_URL}/rest/v1/messages?candidate_id=eq.{cand['id']}&kind=eq.interview_reminder&select=status",
        headers=admin, timeout=20).json()
    check("reminder is a DRAFT (never auto-sent)", bool(msgs) and msgs[0]["status"] == "draft", str(msgs))

    print("\n48h feedback nudge (internal email):")
    past = datetime.now(timezone.utc) - timedelta(days=3)
    httpx.patch(f"{SUPABASE_URL}/rest/v1/interviews?id=eq.{iv['id']}", headers=admin,
                json={"scheduled_start": past.isoformat(),
                      "scheduled_end": (past + timedelta(minutes=30)).isoformat(),
                      "interviewer_email": NUDGE_INBOX}, timeout=20)
    checks = httpx.post(f"{API}/api/scheduler/run-checks", headers=H, json={}, timeout=60).json()
    check("nudge fired", checks.get("nudges_sent", 0) >= 1, str(checks))
    msgs = httpx.get(
        f"{SUPABASE_URL}/rest/v1/messages?candidate_id=eq.{cand['id']}&kind=eq.feedback_nudge&select=status,error",
        headers=admin, timeout=20).json()
    check("nudge email sent via Resend", bool(msgs) and msgs[0]["status"] == "sent", str(msgs))
    checks2 = httpx.post(f"{API}/api/scheduler/run-checks", headers=H, json={}, timeout=60).json()
    check("no duplicate reminder/nudge on re-run",
          checks2.get("reminders_drafted") == 0 and checks2.get("nudges_sent") == 0, str(checks2))

    print("\nFeedback logging:")
    r = httpx.patch(f"{API}/api/interviews/{iv['id']}/feedback", headers=H,
                    json={"feedback": "Strong communication; proceed to offer discussion."}, timeout=20)
    check("feedback logged, interview completed",
          r.status_code == 200 and r.json()["status"] == "completed", f"{r.status_code} {r.text[:200]}")

    print("\nCleanup (cancelling the Google event + removing test rows)...")
    httpx.delete(f"https://www.googleapis.com/calendar/v3/calendars/primary/events/{iv['google_event_id']}?sendUpdates=all",
                 headers={"Authorization": f"Bearer {conn_fresh['access_token']}"}, timeout=20)
    _cleanup(cand["id"])

    print()
    if failures:
        print(f"{len(failures)} check(s) FAILED")
        sys.exit(1)
    print(f"All Phase 4 checks passed. In {CANDIDATE_INBOX} you should see: the scheduling "
          f"invite from Google Calendar, its cancellation, and the feedback-nudge email.")


def _cleanup(candidate_id: str):
    httpx.delete(f"{SUPABASE_URL}/rest/v1/candidates?id=eq.{candidate_id}", headers=admin, timeout=20)


if __name__ == "__main__":
    main()

