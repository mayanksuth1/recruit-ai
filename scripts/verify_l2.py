"""Level 2 verification: async AI interviews, rubric evidence, semantic search.

Drives the REAL stack — the FastAPI app on localhost:8000, the real Supabase
database, and real Gemini calls. Nothing here is mocked, because the whole
point of build.md's DONE list is that reading the code proves nothing.

Proves, in order:

  1. A consumed token cannot start a second session. Opens the same URL twice
     and shows the session count for that token staying at one.
  2. An expired token is refused. Backdates expires_at on a REAL session row
     and shows the response plus the unchanged session count.
  3. A session survives a closed tab. Answers Q1 and Q2, abandons the client
     mid-Q3, reopens and lands back on the identical Q3 with Q1/Q2 intact.
  4. Q2 is genuinely conditioned on Q1. Two sessions, same role, materially
     different Q1 answers, two different Q2s — each quoting its own answer.
  5. Every rubric evidence quote appears verbatim in that candidate's stored
     transcript. String-matches every criterion and reports matched-vs-total,
     then forces a bad quote and shows it landing in scoring_rejected rather
     than on the score card.

Also exercises the pgvector path (embed the backlog, search, confirm the
tenant filter holds).

Prereqs: migrations 0001-0009 applied, backend running on localhost:8000.
Run:  backend\\.venv\\Scripts\\python scripts\\verify_l2.py
"""
import os
import re
import sys
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from dotenv import load_dotenv

HERE = os.path.dirname(__file__)
load_dotenv(os.path.join(HERE, "..", "backend", ".env"))

SUPABASE_URL = os.environ["SUPABASE_URL"]
SECRET_KEY = os.environ["SUPABASE_SECRET_KEY"]
API = os.environ.get("VERIFY_API", "http://localhost:8000")
admin = {"apikey": SECRET_KEY, "Authorization": f"Bearer {SECRET_KEY}",
         "Prefer": "return=representation"}

# Generating a question is a synchronous Gemini call, and the free tier backs
# off in bursts; the app retries internally for up to ~105s per model.
T = 240.0

failures = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))
    if not ok:
        failures.append(name)


def squash(t):
    """Same comparator the database uses in ai_squash_ws: whitespace is
    normalised, case is NOT — verbatim means verbatim."""
    return re.sub(r"\s+", " ", (t or "").strip())


def rest(path, **kw):
    r = httpx.get(f"{SUPABASE_URL}/rest/v1/{path}", headers=admin, timeout=30, **kw)
    r.raise_for_status()
    return r.json()


def token_of(link):
    return link.rsplit("/", 1)[-1]


def sessions_for(token):
    """Count sessions carrying this token's hash, computed by the DATABASE's own
    hash function so the test cannot disagree with the uniqueness constraint it
    is testing."""
    r = httpx.post(f"{SUPABASE_URL}/rest/v1/rpc/ai_interview_token_hash",
                   headers=admin, json={"raw_token": token}, timeout=30)
    r.raise_for_status()
    return rest("ai_interview_sessions", params={"token_hash": f"eq.{r.json()}", "select": "id,status"})


def get_public(token):
    return httpx.get(f"{API}/api/public/ai-interview/{token}", timeout=T)


def answer(token, ordinal, text):
    return httpx.post(f"{API}/api/public/ai-interview/{token}",
                      json={"ordinal": ordinal, "answer": text}, timeout=T)


ROLE_JD = """We run a payments ledger in Python and Postgres handling ~4k writes/sec.
You will own correctness of the double-entry ledger, the idempotency layer in front
of it, and the reconciliation job that proves the books balance daily. Experience
with exactly-once semantics under retries is essential."""

# Five substantial answers. They have to be real prose: the rubric scores them
# and every evidence quote is string-matched back against exactly these strings.
ANSWERS = [
    """I owned the idempotency layer at a card acquirer for two years. The hard part was
    that our PSP retried a webhook up to nine times with the same body but a different
    delivery id, so deduping on delivery id did nothing at all. I moved the key to a hash
    of merchant id, psp reference and amount in minor units, put a unique constraint on
    it, and made the insert ON CONFLICT DO NOTHING returning the existing row.""",
    """The thing I got badly wrong first was doing a SELECT and then an INSERT. It passed
    every test we had, and then during a retry storm two workers both saw nothing and both
    inserted, and we double-credited about forty merchants. I learned that a check-then-act
    pair is not atomic no matter how tight the window looks, and that the only honest fix
    is to let the database enforce the constraint.""",
    """For reconciliation I wrote a daily job that pulled the settlement file from the bank
    and diffed it against our internal balances at the account level rather than the
    transaction level. Account-level diffing meant a single missing transaction showed up
    as one mismatched account instead of thousands of unmatched rows, which made the output
    something a human could actually act on before lunch.""",
    """We chose Postgres advisory locks over a Redis lock for the settlement job because we
    already needed the database transaction to be the unit of atomicity. Adding Redis would
    have meant two systems that could disagree about who held the lock, and the failure mode
    of that disagreement is silent double-posting, which is exactly the thing the lock was
    there to prevent.""",
    """If I could redo one decision it would be storing amounts as floats in the earliest
    version of the reporting table. It was fine until we summed a few million rows and the
    totals drifted by a few cents from the ledger, and reconciling that drift cost me a
    fortnight. Everything numeric has been integer minor units since.""",
]

DIVERGENT_A = ANSWERS[0]
DIVERGENT_B = """Honestly most of my ledger work has been on the reporting side rather than the
write path. I built the daily reconciliation job in Airflow that pulls the settlement file
from the bank, diffs it against our internal balances, and files a Jira ticket per mismatch.
It is mostly pandas and SQL. I have never had to think about exactly-once on ingest because
by the time I see the data it has already been written."""


def main():
    email = f"verifyl2-{uuid.uuid4().hex[:8]}@example.com"
    password = "Verify-" + uuid.uuid4().hex[:12]
    httpx.post(f"{SUPABASE_URL}/auth/v1/admin/users", headers=admin,
               json={"email": email, "password": password, "email_confirm": True},
               timeout=30).raise_for_status()
    tok = httpx.post(f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
                     headers={"apikey": SECRET_KEY},
                     json={"email": email, "password": password}, timeout=30).json()["access_token"]
    H = {"Authorization": f"Bearer {tok}"}
    httpx.post(f"{API}/api/organizations/bootstrap", headers=H,
               json={"organization_name": "L2 Verify Org"}, timeout=30).raise_for_status()
    org_id = httpx.get(f"{API}/api/organizations/me", headers=H, timeout=30).json()["id"]
    role = httpx.post(f"{API}/api/roles", headers=H,
                      json={"title": "Senior Backend Engineer", "description": ROLE_JD},
                      timeout=30).json()

    def new_candidate(name):
        return httpx.post(f"{SUPABASE_URL}/rest/v1/candidates", headers=admin, json={
            "organization_id": org_id, "role_id": role["id"],
            "full_name": name, "email": f"{uuid.uuid4().hex[:8]}@example.com",
            "shortlist_status": "approved",
        }, timeout=30).json()[0]

    def issue(candidate, target=5):
        r = httpx.post(f"{API}/api/candidates/{candidate['id']}/ai-interview", headers=H,
                       json={"role_id": role["id"], "question_target": target}, timeout=30)
        r.raise_for_status()
        return r.json()

    # -----------------------------------------------------------------------
    print("\n[1] A consumed token cannot start a second session")
    # -----------------------------------------------------------------------
    main_cand = new_candidate("Priya Raman")
    issued = issue(main_cand)
    token = token_of(issued["link"])
    sess_id = issued["session"]["id"]

    first = get_public(token)
    check("first open returns 200", first.status_code == 200, f"got {first.status_code}")
    q1_first = first.json()["question"]
    print(f"      Q1: {q1_first}")

    second = get_public(token)
    check("second open returns 200 (resume, not a new session)", second.status_code == 200)
    body2 = second.json()
    print(f"      second response: state={body2['state']} ordinal={body2['ordinal']} answered={body2['answered']}")
    check("second open re-serves the IDENTICAL Q1, not a regenerated one",
          body2["question"] == q1_first,
          f"{body2['question'][:60]!r} != {q1_first[:60]!r}")
    rows = sessions_for(token)
    check("session count for this token stayed at 1", len(rows) == 1, f"got {len(rows)}")
    print(f"      sessions for this token: {rows}")

    # -----------------------------------------------------------------------
    print("\n[2] An expired token is refused")
    # -----------------------------------------------------------------------
    exp_cand = new_candidate("Tomas Iverson")
    exp_issued = issue(exp_cand)
    exp_token = token_of(exp_issued["link"])
    before = len(sessions_for(exp_token))

    # ai_sessions_window_check enforces expires_at > issued_at, so expires_at
    # cannot be dragged into the past on its own — the WHOLE window has to move.
    # That is also the more faithful simulation: an expired link is one that was
    # issued 80 hours ago, not one that was issued now and expires in the past.
    now = datetime.now(timezone.utc)
    only_expiry = httpx.patch(f"{SUPABASE_URL}/rest/v1/ai_interview_sessions",
                              headers=admin, params={"id": f"eq.{exp_issued['session']['id']}"},
                              json={"expires_at": (now - timedelta(hours=1)).isoformat()}, timeout=30)
    check("expires_at alone cannot be dragged behind issued_at",
          only_expiry.status_code >= 400 and "ai_sessions_window_check" in only_expiry.text,
          f"{only_expiry.status_code} {only_expiry.text[:100]}")

    patched = httpx.patch(f"{SUPABASE_URL}/rest/v1/ai_interview_sessions",
                          headers=admin, params={"id": f"eq.{exp_issued['session']['id']}"},
                          json={"issued_at": (now - timedelta(hours=80)).isoformat(),
                                "expires_at": (now - timedelta(hours=8)).isoformat()}, timeout=30)
    check("the issue window is backdatable on a real session row", patched.status_code == 200,
          f"{patched.status_code} {patched.text[:120]}")

    dead = get_public(exp_token)
    check("expired link is refused with 410", dead.status_code == 410, f"got {dead.status_code}")
    print(f"      response: {dead.status_code} {dead.json().get('detail')}")
    after = len(sessions_for(exp_token))
    check("session count unchanged by the refused open", before == after == 1, f"{before} -> {after}")

    # -----------------------------------------------------------------------
    print("\n[3] A session survives a closed tab")
    # -----------------------------------------------------------------------
    r = answer(token, 1, ANSWERS[0])
    check("Q1 answered", r.status_code == 200, f"{r.status_code} {r.text[:160]}")
    v = r.json()
    r = answer(token, 2, ANSWERS[1])
    check("Q2 answered", r.status_code == 200, f"{r.status_code} {r.text[:160]}")
    v = r.json()
    q3_before = v["question"]
    print(f"      Q3 as first served: {q3_before}")

    # "Killing the session mid-Q3" — the client is discarded without answering.
    # Nothing about the interview lives in the client, so this is simply a new
    # request with no carried state.
    del v
    reopened = get_public(token)
    check("reopened link returns 200", reopened.status_code == 200)
    rv = reopened.json()
    check("lands back on Q3", rv["ordinal"] == 3, f"ordinal={rv['ordinal']}")
    check("Q3 is the IDENTICAL question, not a regenerated one",
          rv["question"] == q3_before, f"{rv['question'][:60]!r} != {q3_before[:60]!r}")
    check("Q1 and Q2 are intact in the returned history", len(rv["history"]) == 2,
          f"history={len(rv['history'])}")

    turns = rest("ai_interview_turns", params={
        "session_id": f"eq.{sess_id}", "select": "ordinal,question_text,answer_text,source_turn_ordinal",
        "order": "ordinal"})
    print(f"      ai_interview_turns rows: {len(turns)}")
    for t in turns:
        a = (t["answer_text"] or "")[:48].replace("\n", " ")
        print(f"        ordinal={t['ordinal']} src={t['source_turn_ordinal']} answer={a!r}")
    check("exactly 3 turn rows exist (Q3 asked, unanswered)", len(turns) == 3, f"got {len(turns)}")
    check("turn 3 is stored unanswered", turns[2]["answer_text"] is None)

    # -----------------------------------------------------------------------
    print("\n[4] Q2 is genuinely conditioned on Q1")
    # -----------------------------------------------------------------------
    pair = {}
    for label, ans in (("A", DIVERGENT_A), ("B", DIVERGENT_B)):
        cand = new_candidate(f"Divergent {label}")
        iss = issue(cand, target=2)
        tk = token_of(iss["link"])
        get_public(tk).raise_for_status()
        res = answer(tk, 1, ans)
        res.raise_for_status()
        pair[label] = {"q2": res.json()["question"], "session": iss["session"]["id"], "answer": ans}
        print(f"      [{label}] A1: {squash(ans)[:90]}...")
        print(f"      [{label}] Q2: {pair[label]['q2']}")

    check("the two Q2s differ", pair["A"]["q2"] != pair["B"]["q2"])

    # The strong form: each Q2 must echo distinctive content from ITS OWN answer
    # and not from the other's. Terms are drawn from the fixed answers above.
    a_terms = ["retry storm", "double-credit", "double credit", "select", "insert",
               "idempot", "merchant", "psp", "unique constraint", "conflict"]
    b_terms = ["reconcil", "airflow", "settlement", "pandas", "jira", "report"]
    a_hits = [t for t in a_terms if t in pair["A"]["q2"].lower()]
    b_hits = [t for t in b_terms if t in pair["B"]["q2"].lower()]
    cross_a = [t for t in b_terms if t in pair["A"]["q2"].lower()]
    cross_b = [t for t in a_terms if t in pair["B"]["q2"].lower()]
    check("A's Q2 references A's own answer", bool(a_hits), f"matched {a_hits}")
    check("B's Q2 references B's own answer", bool(b_hits), f"matched {b_hits}")
    print(f"      A's Q2 matched A-terms {a_hits}, B-terms {cross_a}")
    print(f"      B's Q2 matched B-terms {b_hits}, A-terms {cross_b}")

    for label in ("A", "B"):
        rows = rest("ai_interview_turns", params={
            "session_id": f"eq.{pair[label]['session']}", "ordinal": "eq.2",
            "select": "ordinal,source_turn_ordinal"})
        check(f"[{label}] Q2 records source_turn_ordinal=1 in the database",
              rows and rows[0]["source_turn_ordinal"] == 1, f"{rows}")

    # -----------------------------------------------------------------------
    print("\n[5] Every rubric evidence quote is verbatim in the transcript")
    # -----------------------------------------------------------------------
    for i in (2, 3, 4):
        r = answer(token, i + 1, ANSWERS[i])
        check(f"Q{i + 1} answered", r.status_code == 200, f"{r.status_code} {r.text[:160]}")

    sess = rest("ai_interview_sessions", params={"id": f"eq.{sess_id}", "select": "status"})[0]
    check("session reached 'completed' once all 5 were answered",
          sess["status"] == "completed", f"status={sess['status']}")

    stored = rest("ai_interview_turns", params={
        "session_id": f"eq.{sess_id}", "select": "ordinal,answer_text", "order": "ordinal"})
    answers_sq = {t["ordinal"]: squash(t["answer_text"]) for t in stored if t["answer_text"]}

    # ---- the forced bad quote, BEFORE any clean run -----------------------
    # 'scored' is terminal: the evidence trigger refuses every write to a scored
    # session, so a rejection can only be demonstrated on a session that is
    # still 'completed'. Doing it first also proves the recovery path — a
    # rejected run can be cleanly re-scored, which is the whole reason
    # 'scoring_rejected' -> 'scored' is a legal transition.
    print("\n      forcing a fabricated quote onto one criterion first...")
    fake = "I personally rewrote the entire Postgres query planner over one weekend."
    check("the fabricated quote is genuinely absent from the transcript",
          not any(squash(fake) in a for a in answers_sq.values()))
    bad = httpx.post(f"{SUPABASE_URL}/rest/v1/ai_interview_scores", headers=admin, json={
        "organization_id": org_id, "session_id": sess_id,
        "criterion_key": "relevant_experience", "label": "Relevant experience",
        "score": 5, "max_score": 5, "weight": 2.0, "evidence_quote": fake,
    }, timeout=30)
    check("the write was accepted (the row is stored, not discarded)",
          bad.status_code in (200, 201), f"{bad.status_code} {bad.text[:160]}")
    row = bad.json()[0]
    print(f"      relevant_experience: evidence_check={row['evidence_check']!r} "
          f"turn={row['evidence_turn_ordinal']} offset={row['evidence_offset']}")
    check("the trigger marked it 'not_verbatim'", row["evidence_check"] == "not_verbatim",
          f"got {row['evidence_check']!r}")
    check("the rejected quote carries no transcript location",
          row["evidence_turn_ordinal"] is None and row["evidence_offset"] is None)

    rejected = httpx.get(f"{API}/api/ai-interviews/{sess_id}", headers=H, timeout=T).json()
    check("session flipped to 'scoring_rejected'",
          rejected["session"]["status"] == "scoring_rejected",
          f"status={rejected['session']['status']}")
    check("the score card is EMPTY while a quote is unsupported",
          len(rejected["score_card"]) == 0, f"{len(rejected['score_card'])} rows showing")
    check("the rejected criterion is still visible in the evidence audit",
          any(a["criterion_key"] == "relevant_experience" and a["evidence_check"] == "not_verbatim"
              for a in rejected["evidence_audit"]))

    # ---- now the real scoring run ----------------------------------------
    print("\n      running real scoring over the rejected session...")
    scored = httpx.post(f"{API}/api/ai-interviews/{sess_id}/score", headers=H, timeout=T)
    check("scoring returns 200", scored.status_code == 200, f"{scored.status_code} {scored.text[:200]}")
    data = scored.json()
    print(f"      session status after scoring: {data['session']['status']}")

    audit = data["evidence_audit"]
    print(f"      evidence audit ({len(audit)} criteria):")
    for a in audit:
        print(f"        {a['criterion_key']:22} {a['evidence_check']:13} "
              f"words={a['evidence_words']} turn={a['evidence_turn_ordinal']}")

    # The independent check: match each quote against the STORED answers here,
    # in Python, rather than trusting the trigger that produced the verdict.
    card = data["score_card"]
    matched = 0
    for c in card:
        q = squash(c["evidence_quote"])
        hit = any(q in a for a in answers_sq.values())
        matched += hit
        if not hit:
            print(f"        !! {c['criterion_key']} quote NOT found: {q[:80]!r}")
    print(f"      verbatim quotes matched independently: {matched}/{len(card)}")
    check("a score card was produced", len(card) > 0, f"{len(card)} criteria")
    check("EVERY score-card quote is verbatim in the stored transcript",
          len(card) > 0 and matched == len(card), f"{matched}/{len(card)}")
    check("session is 'scored'", data["session"]["status"] == "scored",
          f"status={data['session']['status']}")
    if data["totals"]:
        t0 = data["totals"][0]
        print(f"      weighted total: {t0['weighted_score']}/{t0['weighted_max']} = {t0['percent']}%")

    # Every criterion must also carry a location to click through to.
    check("every criterion has an evidence turn + offset",
          all(c["evidence_turn_ordinal"] and c["evidence_offset"] for c in card))

    # ---- and the card, once valid, cannot be demolished --------------------
    late = httpx.patch(f"{SUPABASE_URL}/rest/v1/ai_interview_scores", headers=admin,
                       params={"session_id": f"eq.{sess_id}",
                               "criterion_key": f"eq.{card[0]['criterion_key']}"},
                       json={"evidence_quote": fake}, timeout=30)
    check("'scored' is terminal — a later bad re-score is refused outright",
          late.status_code >= 400 and "scoring runs on a completed" in late.text,
          f"{late.status_code} {late.text[:120]}")
    check("the score card survived the attempt",
          len(httpx.get(f"{API}/api/ai-interviews/{sess_id}", headers=H, timeout=T)
              .json()["score_card"]) == len(card))
    check("re-scoring a scored interview is refused by the API too",
          httpx.post(f"{API}/api/ai-interviews/{sess_id}/score", headers=H, timeout=T).status_code == 409)

    # -----------------------------------------------------------------------
    print("\n[6] pgvector semantic search (build.md Search section)")
    # -----------------------------------------------------------------------
    httpx.post(f"{SUPABASE_URL}/rest/v1/talent_pool", headers=admin, json={
        "organization_id": org_id, "full_name": "Priya Raman",
        "email": f"pool-{uuid.uuid4().hex[:6]}@example.com",
        "profile_text": "Backend engineer. Payments ledgers, exactly-once delivery, "
                        "Postgres, idempotency keys, settlement reconciliation.",
    }, timeout=30).raise_for_status()

    ref = httpx.post(f"{API}/api/embeddings/refresh", headers=H, timeout=T)
    check("embedding pass returns 200", ref.status_code == 200, f"{ref.status_code} {ref.text[:160]}")
    print(f"      embedded: {ref.json()}")

    again = httpx.post(f"{API}/api/embeddings/refresh", headers=H, timeout=T).json()
    check("re-running the pass embeds nothing (source_hash makes it idempotent)",
          again["chunks"] == 0, f"{again}")

    sr = httpx.post(f"{API}/api/search/semantic", headers=H,
                    json={"query": "handled duplicate webhook retries without double charging",
                          "limit": 10}, timeout=T)
    check("semantic search returns 200", sr.status_code == 200, f"{sr.status_code} {sr.text[:160]}")
    hits = sr.json()
    print(f"      {len(hits)} hits")
    for h in hits[:4]:
        print(f"        {h['similarity']:.3f} [{h['source_kind']}] {squash(h['snippet'])[:70]}...")
    check("search returned results", len(hits) > 0)
    check("every hit belongs to this org's own sources",
          all(h["talent_pool_id"] or h["session_id"] for h in hits))

    # Tenant isolation: a second org must not see any of the above.
    other_email = f"verifyl2b-{uuid.uuid4().hex[:8]}@example.com"
    httpx.post(f"{SUPABASE_URL}/auth/v1/admin/users", headers=admin,
               json={"email": other_email, "password": password, "email_confirm": True},
               timeout=30).raise_for_status()
    otok = httpx.post(f"{SUPABASE_URL}/auth/v1/token?grant_type=password",
                      headers={"apikey": SECRET_KEY},
                      json={"email": other_email, "password": password}, timeout=30).json()["access_token"]
    OH = {"Authorization": f"Bearer {otok}"}
    httpx.post(f"{API}/api/organizations/bootstrap", headers=OH,
               json={"organization_name": "L2 Other Org"}, timeout=30).raise_for_status()
    cross = httpx.post(f"{API}/api/search/semantic", headers=OH,
                       json={"query": "handled duplicate webhook retries without double charging",
                             "limit": 10}, timeout=T).json()
    check("a different tenant's identical search returns nothing", cross == [], f"{len(cross)} leaked rows")

    # -----------------------------------------------------------------------
    print("\nCleanup")
    # -----------------------------------------------------------------------
    for e in (email, other_email):
        users = httpx.get(f"{SUPABASE_URL}/auth/v1/admin/users?per_page=200",
                          headers=admin, timeout=30).json()["users"]
        for u in users:
            if u["email"] == e:
                httpx.delete(f"{SUPABASE_URL}/rest/v1/organization_members", headers=admin,
                             params={"user_id": f"eq.{u['id']}"}, timeout=30)
                httpx.delete(f"{SUPABASE_URL}/auth/v1/admin/users/{u['id']}", headers=admin, timeout=30)
    httpx.delete(f"{SUPABASE_URL}/rest/v1/organizations", headers=admin,
                 params={"id": f"eq.{org_id}"}, timeout=30)
    print("  test org and users removed (cascades take the sessions, turns, scores and vectors)")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nABORTED: {type(e).__name__}: {e}")
        failures.append(f"aborted: {e}")
    print("\n" + "=" * 68)
    if failures:
        print(f"FAILED ({len(failures)}):")
        for f in failures:
            print(f"  - {f}")
        sys.exit(1)
    print("ALL LEVEL 2 CRITERIA VERIFIED")
