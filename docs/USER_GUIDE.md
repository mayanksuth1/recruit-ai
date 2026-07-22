# Recruit AI — Complete User Guide

Everything you need to run and use the platform, step by step. Written for
recruiters using the app day-to-day; the **Admin & troubleshooting** section
at the end covers setup and fixes.

---

## 0. Starting the app (local development)

Two processes need to run. Open two terminals:

**Terminal 1 — backend (API on port 8000):**
```
cd C:\Users\jamba\recruit-ai\backend
.venv\Scripts\python -m uvicorn app.main:app --port 8000
```

**Terminal 2 — frontend (app on port 5173):**
```
cd C:\Users\jamba\recruit-ai\frontend
npm run dev
```

Then open **http://localhost:5173** in your browser.

> Tip: if the backend won't start with "only one usage of each socket
> address", an old copy is still holding port 8000 — kill it first:
> `Get-NetTCPConnection -LocalPort 8000 | % { Stop-Process -Id $_.OwningProcess -Force }`

**Current login:** `mayankdigikit@gmail.com` / `RecruitAI@2026`

---

## 1. Sign up & workspace

1. Open the app → **Sign up**.
2. Enter an **organization name** (this becomes your isolated workspace —
   every role, candidate, and email lives inside it; other organizations can
   never see your data), your email, and a password (8+ characters).
3. You land on the **Roles** page of your new workspace.

Multiple recruiters can share one organization (currently added via the
database; a UI invite flow is a future addition). One login = one
organization.

---

## 2. Roles — define what you're hiring for

**Page: Roles (home)**

1. In the **New role** card, enter the role title (e.g. *Senior Backend
   Engineer*) and paste the **full job description** into the description box.
   The JD matters: every AI score is computed against it.
2. Click **Create role**. It appears in the list below; click it to open the
   role workspace.

---

## 3. Getting candidates in (Sourcing & Screening)

You have three ways to add candidates. All of them feed the same ranked
shortlist on the role page.

### 3a. Upload resume PDFs
On a role page, click the dashed **"Upload resume PDF(s)"** box and pick one
or more PDFs. For each resume the AI:
- extracts the candidate's name, email, and phone,
- scores it 0–100 against the JD (with skills / experience / education
  sub-scores and a written rationale),
- adds the person to your org-wide **Talent Pool** so they persist across roles.

Scanned-image PDFs without extractable text are rejected — you'll see a clear
error.

### 3b. Import a CSV (e.g. exported LinkedIn search results)
**Page: Talent Pool**

1. Click the dashed upload box and pick a `.csv` file — or paste CSV rows
   into the text area and click **Import pasted rows**.
2. Column headers are matched flexibly: `Name` / `Full Name` / `Candidate`,
   `Email`, `Phone` / `Mobile`, `Title` / `Designation`, `Company` /
   `Employer`, `Location`, `Years of Experience` / `YoE`, `Skills`,
   `Summary` / `Notes` all work. Unrecognized columns aren't lost — they're
   folded into the candidate's profile text.
3. **Duplicates are handled automatically**: a row matching an existing
   person by email updates them; a near-identical name backed by the same
   phone or company merges too. Genuinely ambiguous cases import as new and
   get flagged. Use **Scan for duplicates** anytime for a review-only report
   of suspected pairs.

A ready-made sample file lives at `scripts/mock_candidates_20.csv`.

> **Why no live LinkedIn scraping?** There's no public API and scraping
> violates LinkedIn's terms (risking account bans). Export search results to
> CSV and import them. If you ever get partner-tier LinkedIn Recruiter API
> access, the integration point is `backend/app/sourcing/connectors/linkedin.py`.

### 3c. Match the pool against a role
On a role page, click **Match from talent pool**. Every pool candidate not
already attached to the role is scored against the JD in batches and appears
in the ranked list. Great for checking a new role against everyone you've
ever sourced.

### Bonus: Boolean search strings
On a role page, click **Generate Boolean search** — the AI turns the JD into
a LinkedIn people-search string and a Google X-ray string, each with a copy
button, plus tuning tips.

---

## 4. The shortlist — Human Approval Gate 1

Candidates on a role page are ranked by score (colored blob: green = strong,
yellow = middling, pink = weak). For each candidate:

- **Approve** — marks them *approved*. This is **gate 1**: only approved
  candidates can receive outreach or be scheduled.
- **Reject** / **Reset** — take them out of, or back to, consideration.
- Use the checkboxes + **Select all** for **bulk approve/reject**.

Nothing here contacts anyone — approval only unlocks the next step.

---

## 5. Outreach emails (Engagement)

**The golden rule everywhere: no email ever reaches a candidate without your
explicit click on Send.** The AI only writes drafts.

1. On an approved candidate, click **Draft outreach**. The AI writes a
   personalized first-contact email using the JD + their profile (it cites
   real details from their background — no invented facts, no salary
   promises).
2. Go to the **Outbox** page → **Drafts** tab. Edit the subject or body
   inline if you like.
3. Click **Send** → confirm. The email goes out via Resend and moves to the
   **Sent** tab. Or click **Discard** to kill it.
4. **Stage changes draft status updates too**: when you move a candidate's
   stage dropdown (e.g. to *interview*), a status-update email is drafted —
   again, it just waits in the Outbox for your review.
5. **Follow-ups**: in the Outbox header, set the day threshold (default 4)
   and click **Draft follow-ups**. Every sent outreach that got no reply in
   that window gets a polite follow-up draft — one per thread, never
   duplicated. When a candidate replies, click **mark replied** on the sent
   message to stop the sequence.

---

## 6. Scheduling interviews

### One-time setup (per recruiter)
**Page: Settings** → **Connect Google Calendar** → sign into the Google
account whose calendar you use → (on the "unverified app" warning:
*Advanced → Go to app*) → **Allow**. Settings then shows "Connected as …".

### Scheduling flow
1. On an approved candidate, click **Schedule interview**. Set the duration,
   optionally add a hiring manager's email (they'll be on the invite), and
   click **Propose slots + draft email**.
2. The system reads your **real Google Calendar free/busy** and proposes open
   weekday slots (10:00–18:00 IST by default). A scheduling-link email is
   drafted into the **Outbox** — review and **Send** it (gate 1 applies).
3. **The candidate books themselves**: the email contains a private link to a
   no-login page listing your open slots. They pick one; a Google Calendar
   event with a **Meet link** is created instantly and Google emails the
   invite to everyone.
4. Track everything on the **Interviews** page: status, times, Meet links.

### Automation around the interview
- **24h before**: a reminder email to the candidate is **drafted** into the
  Outbox (you still click Send).
- **48h after** with no feedback logged: the **interviewer** gets an
  automatic internal nudge email (this is the one automatic email — it never
  goes to a candidate or client).
- These checks run every 15 minutes; **Run checks now** on the Interviews
  page triggers them on demand.
- Log feedback in the interview card's text box — this completes the
  interview and stops nudges. **Cancel** removes the calendar event.

---

## 7. Offers & closing — Human Approval Gate 2

Moving a candidate to the **offer** or **closed** stage is blocked until a
human explicitly approves it:

1. On the candidate card, click **Approve for offer** (it records who and
   when; click again to revoke).
2. Only then does the stage dropdown accept *offer* / *closed*.

Gate 2 also binds external systems: an ATS pushing "offer" through the
webhook gets rejected until someone approved it here first.

---

## 8. ATS sync (optional)

**Page: Settings → ATS sync.** Works with any ATS that speaks webhooks
(Greenhouse/Lever style). Workday needs its paid enterprise API tier —
arranged separately.

- **Outbound**: paste your ATS's webhook URL; every stage change and offer
  approval is POSTed there as signed JSON
  (`X-RecruitAI-Signature: sha256=…` HMAC using your shared secret).
  **Send test event** fires a hello-world to verify wiring.
- **Inbound**: give your ATS the displayed inbound URL. It can push
  `{"event": "candidate.stage_changed", "candidate_email": "…", "stage": "…"}`
  and the candidate updates here.
- Every event, both directions, is logged in the panel below
  (delivered / failed / applied / rejected).

---

## 9. Reports

**Page: Reports.**

- **Hiring funnel**: sourced → screened → outreached → interviewed →
  offered → closed, with per-stage drop-off percentages and a per-role
  breakdown table.
- **Two views** (toggle at the top): **Recruiter view** shows everything
  including upcoming interviews and pending drafts; **Client view** shows
  aggregate numbers and role titles only — zero candidate PII, safe to
  screen-share with clients.
- **Weekly summaries**: auto-generated every week (stored, never emailed).
  **Generate this week** creates one on demand; **Download PDF** produces a
  shareable summary document (aggregate data only).

---

## 10. Admin & troubleshooting

| Symptom | Cause & fix |
|---|---|
| "Invalid login credentials" | Wrong password. There's no self-serve reset yet — an admin resets it via Supabase (dashboard → Authentication → Users, or admin API). |
| "Email not confirmed" at sign-in | The Supabase confirmation link didn't register. Fix the **Site URL** in Supabase Auth settings, or confirm the user in dashboard → Authentication → Users. |
| Page shows an error once, works on reload | Free-tier Supabase intermittently drops idle connections. The app retries automatically now; persistent failures mean Supabase itself is down. |
| Scoring fails with "temporarily unavailable" | Gemini free-tier quota exhausted or overloaded. Wait, or switch models via `GEMINI_MODEL` in `backend/.env` (per-model quotas), or enable billing on the Google AI project. |
| Emails only arrive at one inbox | Resend sandbox: without a verified domain, delivery is restricted to the Resend account owner's address. Verify a domain in Resend to email real candidates. |
| Calendar connect fails with `redirect_uri_mismatch` | Add `http://localhost:8000/api/calendar/oauth/callback` to the OAuth client's **Authorized redirect URIs** in Google Cloud Console. |
| Calendar API 403 | Enable the **Google Calendar API** for the Google Cloud project. |

**Configuration** lives in `backend/.env` (Supabase keys, Gemini key/models,
Resend key, Google OAuth, timezone, scheduler interval) and `frontend/.env`
(Supabase URL + publishable key). Never put the secret key in the frontend.

**Database migrations** are in `supabase/migrations/` (0001–0006). Apply new
ones via the Supabase SQL editor, or through the `admin_exec_sql` RPC if you
installed the optional `0000_optional_admin_exec.sql` helper.

**Verification suites** — every module has a re-runnable proof:
```
backend\.venv\Scripts\python scripts\verify_phase1.py   # tenant isolation (RLS)
backend\.venv\Scripts\python scripts\verify_phase2.py   # CSV import + AI ranking
backend\.venv\Scripts\python scripts\verify_phase3.py   # gate 1 + email flow (sends real email)
backend\.venv\Scripts\python scripts\verify_phase4.py   # scheduling (books real calendar event)
backend\.venv\Scripts\python scripts\verify_phase5.py   # gate 2 + ATS webhooks + dedup
backend\.venv\Scripts\python scripts\verify_phase6.py   # reporting accuracy + PDF
```

**The two non-negotiables**, enforced in code, not policy:
1. No message reaches a candidate or client without an explicit human click.
2. Offer/closure stages require a recorded human approval — including for
   changes pushed by external systems.
