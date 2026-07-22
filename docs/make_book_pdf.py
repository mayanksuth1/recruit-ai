"""Render The Recruit AI Book as a styled PDF (pastel identity of the app)."""
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (Flowable, PageBreak, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

OUT = r"C:\Users\jamba\recruit-ai\docs\recruit-ai-book.pdf"

# ---- palette -------------------------------------------------------------
CREAM = HexColor("#F6EFE9")
CARD = HexColor("#FFFDFB")
COCOA = HexColor("#52463F")
SOFT = HexColor("#7A6E64")
FAINT = HexColor("#A79A8F")
LINE = HexColor("#E7DCD3")
PEACH = HexColor("#F4BFA4")
LAVENDER = HexColor("#C7C5EE")
MINT = HexColor("#B9E2D8")
BABYBLUE = HexColor("#B7D6EE")
BUTTER = HexColor("#F4DCA6")
ROSY = HexColor("#F0B3BF")

PAGE_W, PAGE_H = A4
M = 20 * mm

# ---- styles --------------------------------------------------------------
def st(name, **kw):
    base = dict(fontName="Helvetica", fontSize=10.5, leading=16, textColor=SOFT)
    base.update(kw)
    return ParagraphStyle(name, **base)

S = {
    "title": st("title", fontName="Helvetica-Bold", fontSize=34, leading=40, textColor=COCOA),
    "lede": st("lede", fontSize=12.5, leading=19),
    "eyebrow": st("eyebrow", fontName="Helvetica-Bold", fontSize=8.5, leading=12,
                  textColor=FAINT, spaceAfter=4),
    "h2": st("h2", fontName="Helvetica-Bold", fontSize=20, leading=25, textColor=COCOA, spaceAfter=8),
    "h3": st("h3", fontName="Helvetica-Bold", fontSize=13, leading=17, textColor=COCOA,
             spaceBefore=14, spaceAfter=4),
    "body": st("body", spaceAfter=7),
    "li": st("li", leftIndent=14, bulletIndent=4, spaceAfter=4),
    "step": st("step", leftIndent=20, firstLineIndent=-20, spaceAfter=5),
    "code": st("code", fontName="Courier", fontSize=8.8, leading=13, textColor=COCOA,
               backColor=HexColor("#EFE6DD"), borderPadding=(6, 8, 6, 8), spaceAfter=8),
    "callout_label": st("cl", fontName="Helvetica-Bold", fontSize=8, leading=11, textColor=COCOA),
    "callout": st("co", fontSize=10, leading=15, textColor=COCOA),
    "cell": st("cell", fontSize=9, leading=13),
    "cellb": st("cellb", fontName="Helvetica-Bold", fontSize=9, leading=13, textColor=COCOA),
    "th": st("th", fontName="Helvetica-Bold", fontSize=7.5, leading=10, textColor=FAINT),
    "footer": st("footer", fontSize=8.5, textColor=FAINT),
}


def B(text):  # cocoa bold inline
    return f'<font color="#52463F"><b>{text}</b></font>'


# ---- custom flowables ----------------------------------------------------
class Dots(Flowable):
    def __init__(self, r=5.2, gap=4, colors=(PEACH, LAVENDER, MINT)):
        super().__init__()
        self.r, self.gap, self.colors = r, gap, colors
        self.height = r * 2 + 2

    def draw(self):
        x = self.r
        for c in self.colors:
            self.canv.setFillColor(c)
            self.canv.circle(x, self.r, self.r, stroke=0, fill=1)
            x += self.r * 2 + self.gap


class FunnelBar(Flowable):
    def __init__(self, label, frac, color, width=150 * mm):
        super().__init__()
        self.label, self.frac, self.color, self.w = label, frac, color, width
        self.height = 9.2 * mm

    def draw(self):
        c = self.canv
        h = 7.4 * mm
        bw = max(self.w * self.frac, 34 * mm)
        c.setFillColor(self.color)
        c.roundRect(0, 1, bw, h, h / 2, stroke=0, fill=1)
        c.setFillColor(COCOA)
        c.setFont("Helvetica-Bold", 8.6)
        c.drawString(5 * mm, 1 + h / 2 - 3, self.label)


class Chip(Flowable):
    """Row of pill chips."""
    def __init__(self, items):  # [(text, color)]
        super().__init__()
        self.items = items
        self.height = 8.5 * mm

    def draw(self):
        c = self.canv
        x = 0
        for text, color in self.items:
            w = c.stringWidth(text, "Helvetica-Bold", 8.6) + 9 * mm
            c.setFillColor(color)
            c.roundRect(x, 1, w, 6.4 * mm, 3.2 * mm, stroke=0, fill=1)
            c.setFillColor(COCOA)
            c.setFont("Helvetica-Bold", 8.6)
            c.drawCentredString(x + w / 2, 1 + 3.2 * mm - 3, text)
            x += w + 3 * mm


def callout(label, lines, color):
    rows = [[Paragraph(label.upper(), S["callout_label"])]] + [[Paragraph(t, S["callout"])] for t in lines]
    t = Table(rows, colWidths=[150 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), color),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, 0), 10),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 10),
        ("TOPPADDING", (0, 1), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -2), 2),
        ("ROUNDEDCORNERS", [10, 10, 10, 10]),
    ]))
    return t


def data_table(headers, rows, widths):
    data = [[Paragraph(h.upper(), S["th"]) for h in headers]]
    for r in rows:
        data.append([Paragraph(cell, S["cellb"] if i == 0 else S["cell"]) for i, cell in enumerate(r)])
    t = Table(data, colWidths=widths, repeatRows=1)
    style = [
        ("LINEBELOW", (0, 0), (-1, 0), 1.2, LINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    for i in range(1, len(data) - 1):
        style.append(("LINEBELOW", (0, i), (-1, i), 0.5, LINE))
    t.setStyle(TableStyle(style))
    return t


def chapter_head(num, color, title):
    return [
        Paragraph(f'<font color="#{color.hexval()[2:]}">•</font>&nbsp;&nbsp;CHAPTER {num}', S["eyebrow"]),
        Paragraph(title, S["h2"]),
    ]


def steps(items):
    out = []
    for i, text in enumerate(items, 1):
        out.append(Paragraph(f"{B(str(i) + '.')}&nbsp;&nbsp;{text}", S["step"]))
    return out


def bullets(items):
    return [Paragraph(t, S["li"], bulletText="•") for t in items]


# ---- page furniture ------------------------------------------------------
def on_page(canv, doc):
    canv.saveState()
    canv.setFillColor(CREAM)
    canv.rect(0, 0, PAGE_W, PAGE_H, stroke=0, fill=1)
    if doc.page > 1:
        canv.setFillColor(FAINT)
        canv.setFont("Helvetica", 8.2)
        canv.drawString(M, 11 * mm, "The Recruit AI Book")
        canv.drawRightString(PAGE_W - M, 11 * mm, str(doc.page))
        for i, c in enumerate((PEACH, LAVENDER, MINT)):
            canv.setFillColor(c)
            canv.circle(PAGE_W / 2 - 5 * mm + i * 5 * mm, 12.2 * mm, 1.5 * mm, stroke=0, fill=1)
    canv.restoreState()


# ---- content -------------------------------------------------------------
story = []

# Cover
story += [
    Spacer(1, 40 * mm),
    Dots(),
    Spacer(1, 8 * mm),
    Paragraph("THE COMPLETE OWNER'S MANUAL", S["eyebrow"]),
    Paragraph("The Recruit AI Book", S["title"]),
    Spacer(1, 6 * mm),
    Paragraph("Everything about the recruitment automation platform: what it does and who "
              "it's for, how it was designed and built, how to set it up from zero, how to "
              "run it every day, and how to hand it to a paying client.", S["lede"]),
    Spacer(1, 10 * mm),
    Chip([("6 modules", PEACH), ("2 human approval gates", LAVENDER),
          ("Multi-tenant", MINT), ("88 automated checks", BABYBLUE)]),
    Spacer(1, 46 * mm),
    Paragraph("Built and documented by Claude for Mayank · 2026", S["footer"]),
    PageBreak(),
]

# Chapter 1
story += chapter_head(1, PEACH, "What Recruit AI is")
story.append(Paragraph(
    f"Recruit AI is a {B('multi-tenant recruitment automation platform')}. One installation "
    "serves many recruiting organizations; each organization's roles, candidates, emails, and "
    "reports are invisible to every other. AI does the heavy reading and writing — scoring "
    "resumes, ranking talent pools, drafting personalized emails — while humans keep control "
    "of every moment that touches a candidate or a client.", S["body"]))
story.append(Spacer(1, 3 * mm))
story.append(callout("The two non-negotiables (enforced in code, not policy)", [
    f"{B('1.')} No email ever reaches a candidate or client without an explicit human click. The AI only writes drafts.",
    f"{B('2.')} Moving anyone to the offer or closed stage requires a recorded human approval — even when the change comes from an external ATS.",
], BUTTER))
story.append(Paragraph("The six modules", S["h3"]))
story.append(data_table(["Module", "What it does"], [
    ["Sourcing", "CSV / paste import of candidate lists (e.g. exported LinkedIn searches), an org-wide talent pool that persists across roles, an AI Boolean-search generator, and automatic duplicate detection."],
    ["Screening &amp; Scoring", "Resume PDFs and pool profiles scored 0–100 against a job description, with sub-scores, a written rationale, and a ranked shortlist with bulk approve/reject."],
    ["Engagement", "AI-drafted personalized outreach, status updates on stage changes, and no-reply follow-ups — all queued in an Outbox for review before a human sends them."],
    ["Scheduling", "Google Calendar per recruiter: slots proposed from real availability, a no-login booking link for candidates, automatic Meet links, 24-hour reminder drafts, 48-hour feedback nudges."],
    ["Data &amp; ATS Sync", "Generic signed webhooks in both directions — works with any webhook-capable ATS (Greenhouse/Lever style) — plus fuzzy duplicate merging on import."],
    ["Reporting", "A live hiring funnel with drop-off rates, a detailed recruiter dashboard, a PII-free client view, and weekly summaries stored and downloadable as PDF."],
], [32 * mm, 118 * mm]))
story.append(Paragraph("The pipeline at a glance", S["h3"]))
for label, frac, color in [
    ("Sourced — everyone who enters the system", 1.0, PEACH),
    ("Screened — scored against a JD", 0.86, BUTTER),
    ("Outreached — a human sent the email", 0.66, MINT),
    ("Interviewed — booked on a real calendar", 0.46, BABYBLUE),
    ("Offered — behind approval gate 2", 0.30, LAVENDER),
    ("Closed", 0.18, ROSY),
]:
    story.append(FunnelBar(label, frac, color))
story.append(PageBreak())

# Chapter 2
story += chapter_head(2, LAVENDER, "Use cases &amp; playbooks")
story.append(Paragraph("Who it's for", S["h3"]))
story += bullets([
    f"{B('Recruiting agencies')} placing candidates for client companies — each engagement gets clean funnel reporting, and the client-facing dashboard shares progress without exposing candidate identities.",
    f"{B('In-house talent teams')} that want AI leverage on screening volume without surrendering the candidate relationship to automation.",
    f"{B('Staffing firms')} sitting on years of spreadsheets — the talent pool turns old sourcing lists into a searchable, re-scorable asset.",
])
story.append(Paragraph("Playbook: fill a backend role this month", S["h3"]))
story += steps([
    "Create the role and paste the full job description — every score derives from it.",
    "Import your exported LinkedIn search as CSV into the Talent Pool, and upload any direct-applicant resume PDFs on the role page.",
    f"Click {B('Match from talent pool')} — everyone you've ever sourced gets ranked against this JD in minutes.",
    "Sweep the shortlist: bulk-approve the top band, reject the clear noes.",
    "Draft outreach for each approved candidate; polish and send from the Outbox in one sitting.",
    f"After four days, click {B('Draft follow-ups')} — silent threads get a polite nudge, written for you.",
    "For candidates who reply, propose interview slots — they self-book from your live calendar, and the Meet invite handles itself.",
    "Log feedback after each interview (the system nudges the interviewer if you forget), approve for offer, close, and pull the weekly PDF for the hiring manager.",
])
story.append(Paragraph("Playbook: reactivate a dead spreadsheet", S["h3"]))
story += steps([
    "Export the old tracker to CSV — the importer maps flexible headers (Name/Full Name, YoE/Experience, Employer/Company…) and folds unknown columns into the profile text so nothing is lost.",
    "Import. Duplicates merge automatically on email, or on near-identical names corroborated by phone/company; ambiguous pairs are flagged for human review, never auto-merged.",
    "Open any live role and match the pool against it — dormant candidates often rank surprisingly well against new JDs.",
])
story.append(Paragraph("Playbook: the Friday client report", S["h3"]))
story += steps([
    f"Open Reports and flip to {B('Client view')} — aggregate funnel, drop-offs, and role names only; candidate PII is excluded by construction, so it's safe to screen-share.",
    "Download the weekly PDF (auto-generated every week; stored, never auto-emailed) and attach it to your own client email.",
])
story.append(PageBreak())

# Chapter 3
story += chapter_head(3, MINT, "How it was built")
story.append(Paragraph(
    "The platform was built by Claude (Anthropic's AI) in six phases over a working session "
    "with Mayank, each phase ending with a hard verification gate: an automated script proving "
    "the phase's promise against real services — real database, real AI calls, a real email in "
    "a real inbox, a real event on a real Google Calendar. No phase advanced until its gate "
    "passed. Those scripts remain in <font face='Courier' size='9'>scripts/verify_phase1-6.py</font> "
    "and can be re-run anytime.", S["body"]))
story.append(Paragraph("The stack", S["h3"]))
story.append(data_table(["Layer", "Technology", "Why"], [
    ["Frontend", "React (Vite) + Tailwind v4", "Fast dev loop; the pastel design system lives in ~40 lines of theme tokens."],
    ["Backend", "FastAPI (Python)", "One router per module; typed request models; trivially deployable."],
    ["Database + Auth", "Supabase (Postgres + GoTrue)", "Row Level Security gives real multi-tenancy at the database layer."],
    ["AI", "Gemini (2.5 flash family)", "Structured-output JSON for scoring and drafting; env-switchable models with fallback."],
    ["Email", "Resend", "One clean REST call; sandbox mode for safe development."],
    ["Calendar", "Google Calendar API", "Free/busy for slot proposals; events with Meet links; OAuth per recruiter."],
    ["PDF", "fpdf2", "Weekly summaries rendered on demand."],
], [28 * mm, 42 * mm, 80 * mm]))
story.append(Paragraph("The multi-tenancy design", S["h3"]))
story.append(Paragraph(
    "Every data table carries an organization id and a Row Level Security policy: a member of "
    "one organization physically cannot read another's rows, even talking to the database "
    "directly. The backend uses a service key (which bypasses RLS) and therefore scopes every "
    "single query by the organization resolved from the caller's verified JWT — a "
    "belt-and-braces design verified by a test that tries, and fails, to cross the boundary "
    "both through the API and through the database itself.", S["body"]))
story.append(Paragraph("The approval gates as code", S["h3"]))
story.append(Paragraph(
    "Gate 1: outreach can only be drafted for shortlist-approved candidates, and the only code "
    "path that sends an email is the explicit send endpoint behind the Outbox button. Gate 2: "
    "the offer/closed stages reject any transition — from the UI or from an inbound ATS "
    "webhook — until a recruiter has recorded an offer approval. The single automatic email in "
    "the whole system is the internal feedback nudge to the interviewer, which never goes to a "
    "candidate or client.", S["body"]))
story.append(Paragraph("Deliberate boundaries", S["h3"]))
story += bullets([
    f"{B('No LinkedIn scraping.')} It violates LinkedIn's terms and risks account bans; sourcing works via CSV export/import, with a clean integration point stubbed for the partner-only Recruiter API.",
    f"{B('WhatsApp is stubbed.')} The official Business Platform API requires Meta verification; engagement is email-first behind an interface WhatsApp can slot into later.",
    f"{B('Workday flagged, not faked.')} The ATS layer speaks generic webhooks; Workday's enterprise API tier is a commercial arrangement, not a code problem.",
])
story.append(Paragraph("Real bugs found by the verification gates", S["h3"]))
story.append(data_table(["Bug", "Found by", "Fix"], [
    ["Gemini client garbage-collected mid-request", "Phase 2 batch scoring failing", "Singleton client"],
    ["Free-tier model quotas are per-model", "Repeated 429/503 during verification", "Retry + env-switchable primary/fallback models"],
    ["strip(\" at\") ate letters — \"Zeta\" became \"Ze\"", "Reading ranked output line by line", "Proper join + regression check"],
    ["Batch scoring silently skipped candidates", "Assertion that all 20 imports must score", "Straggler re-scoring passes"],
    ["Supabase free tier drops idle connections", "Intermittent one-off 500s", "Retrying transport, keep-warm ping, client GET retry"],
], [52 * mm, 50 * mm, 48 * mm]))
story.append(Paragraph(
    "That table is the honest argument for verification-driven building: every one of these "
    "would otherwise have surfaced in front of a client.", S["body"]))
story.append(PageBreak())

# Chapter 4
story += chapter_head(4, BABYBLUE, "Setting it up from zero")
story.append(Paragraph("Four free-tier accounts, two env files, six migrations, two processes. "
                       "Roughly an hour the first time.", S["body"]))
story.append(Paragraph("1 · Accounts and keys", S["h3"]))
story.append(data_table(["Service", "What you need", "Where"], [
    ["Supabase", "A project; its URL, secret key (backend only), publishable key (frontend)", "supabase.com -> Project Settings -> API Keys"],
    ["Google AI Studio", "A Gemini API key", "aistudio.google.com/apikey"],
    ["Resend", "An API key (sandbox is fine to start)", "resend.com -> API Keys"],
    ["Google Cloud", "OAuth web client (ID + secret), Calendar API enabled, redirect URI http://localhost:8000/api/calendar/oauth/callback", "console.cloud.google.com -> Credentials"],
], [30 * mm, 72 * mm, 48 * mm]))
story.append(Paragraph("2 · Configuration", S["h3"]))
story.append(Paragraph(
    "Copy backend/.env.example -> backend/.env and fill in the keys above. Copy "
    "frontend/.env.example -> frontend/.env with the Supabase URL and publishable key. "
    f"{B('The secret key must never appear in the frontend.')}", S["body"]))
story.append(Paragraph("3 · Database", S["h3"]))
story.append(Paragraph(
    "Run each file in supabase/migrations/ (0001 -> 0006, in order) in the Supabase SQL editor. "
    "The optional 0000_optional_admin_exec.sql installs a service-role-only RPC so future "
    "migrations can be applied programmatically — convenient, with the trade-off documented in "
    "the file.", S["body"]))
story.append(Paragraph("4 · Run it", S["h3"]))
story.append(Paragraph(
    "# terminal 1 — backend<br/>"
    "cd backend<br/>"
    "python -m venv .venv<br/>"
    ".venv\\Scripts\\pip install -r requirements.txt<br/>"
    ".venv\\Scripts\\python -m uvicorn app.main:app --port 8000<br/><br/>"
    "# terminal 2 — frontend<br/>"
    "cd frontend<br/>"
    "npm install<br/>"
    "npm run dev", S["code"]))
story.append(Paragraph("Open http://localhost:5173, sign up, and your organization exists.", S["body"]))
story.append(Paragraph("5 · Prove it works", S["h3"]))
story.append(Paragraph(
    "backend\\.venv\\Scripts\\python scripts\\verify_phase1.py&nbsp;&nbsp;&nbsp;# tenant isolation<br/>"
    "backend\\.venv\\Scripts\\python scripts\\verify_phase2.py&nbsp;&nbsp;&nbsp;# import + AI ranking<br/>"
    "backend\\.venv\\Scripts\\python scripts\\verify_phase5.py&nbsp;&nbsp;&nbsp;# gates + webhooks<br/>"
    "backend\\.venv\\Scripts\\python scripts\\verify_phase6.py&nbsp;&nbsp;&nbsp;# reporting + PDF", S["code"]))
story.append(Paragraph(
    "(Phases 3 and 4 also have suites, but they send a real email and book a real calendar "
    "event — run them deliberately.)", S["body"]))
story.append(PageBreak())

# Chapter 5
story += chapter_head(5, BUTTER, "The operating manual")
story.append(Paragraph("Daily rhythm", S["h3"]))
story += steps([
    f"{B('Roles')} — create a role with its full JD; open it to work a pipeline.",
    f"{B('Add candidates')} — resume PDFs on the role page, CSVs on the Talent Pool page, or Match from talent pool to score everyone you already have.",
    f"{B('Shortlist')} — approve/reject (singly or in bulk). Approval is gate 1: it contacts no one, it only unlocks contact.",
    f"{B('Outbox')} — every AI-drafted email waits here. Edit inline, then Send or Discard. Set the follow-up window and click Draft follow-ups for silent threads; mark replied stops a sequence.",
    f"{B('Schedule')} — on an approved candidate: duration, optional hiring-manager email, Propose slots + draft email. Send the drafted link; the candidate self-books; the Meet invite is automatic.",
    f"{B('Interviews')} — statuses, Meet links, feedback logging. Reminder drafts appear 24h before; interviewers get nudged 48h after if feedback is missing; Run checks now forces a pass.",
    f"{B('Offer')} — click Approve for offer (gate 2), then move the stage to offer/closed.",
    f"{B('Reports')} — funnel with drop-offs, recruiter/client view toggle, weekly PDF downloads.",
])
story.append(Paragraph("Settings, once per recruiter", S["h3"]))
story += bullets([
    f"{B('Google Calendar')} — connect the account whose calendar interviews should land on.",
    f"{B('ATS sync')} — paste the ATS's webhook URL and a shared secret; give the ATS your displayed inbound URL. Test with Send test event; watch the live log below it.",
])
story.append(Spacer(1, 4 * mm))
story.append(callout("Mental model", [
    "The AI is a tireless junior recruiter who reads everything and drafts everything, but "
    "owns no Send button, no offer, and no client relationship. Those are yours.",
], MINT))
story.append(PageBreak())

# Chapter 6
story += chapter_head(6, ROSY, "Limits &amp; troubleshooting")
story.append(Paragraph("Known limits (by design or by tier)", S["h3"]))
story += bullets([
    f"{B('Resend sandbox')} delivers only to the Resend account owner's inbox until you verify a sending domain — perfect for testing, useless for real candidates. Verify a domain before go-live.",
    f"{B('Gemini free tier')} has per-model daily quotas; heavy scoring days can exhaust one. The app falls back automatically, and GEMINI_MODEL / GEMINI_FALLBACK_MODEL in backend/.env switch models without code changes. Billing removes the ceiling.",
    f"{B('Supabase free tier')} occasionally drops idle connections or responds slowly. The app retries transparently; a persistent outage is upstream, not local.",
    f"{B('Unverified Google OAuth app')} shows a warning screen during calendar connect (Advanced -> Go to app). Google's verification process removes it.",
    f"{B('No LinkedIn scraping, WhatsApp stubbed, Workday commercial')} — see Chapter 3.",
])
story.append(Paragraph("Symptom -> fix", S["h3"]))
story.append(data_table(["Symptom", "Fix"], [
    ["\"Invalid login credentials\"", "Password is wrong; an admin resets it in Supabase -> Authentication -> Users. (Self-serve reset is a sensible next feature.)"],
    ["\"Email not confirmed\" at sign-in", "Set the Site URL in Supabase Auth settings so confirmation links resolve, or confirm the user from the Supabase dashboard."],
    ["Scoring \"temporarily unavailable\"", "Quota or load spike — wait, switch models via env, or enable billing."],
    ["Calendar connect -> redirect_uri_mismatch", "The redirect URI isn't registered on the OAuth client (Authorized redirect URIs — not the JavaScript-origins box)."],
    ["Calendar calls -> 403", "Enable the Google Calendar API for the project."],
    ["Backend won't start: port in use", "An old process holds port 8000 — kill it and relaunch."],
], [58 * mm, 92 * mm]))
story.append(PageBreak())

# Chapter 7
story += chapter_head(7, PEACH, "Delivering it to a client")
story.append(Paragraph("Choose the shape", S["h3"]))
story += bullets([
    f"{B('One shared installation, one organization per client')} — the multi-tenant design exists exactly for this. Cheapest to run; you operate it as a service.",
    f"{B('Dedicated installation per client')} — their own Supabase project and keys. More setup, total data separation, easiest story for security-sensitive clients.",
])
story.append(Paragraph("Production checklist", S["h3"]))
story += steps([
    f"{B('Fresh credentials.')} New Supabase project (or at minimum rotated keys), new Gemini key, new Resend key, new Google OAuth client. Never reuse development keys that have been shared in chats or screenshots.",
    f"{B('Verify a sending domain in Resend')} (e.g. talent.clientname.com) and set EMAIL_FROM — this is what makes candidate email real.",
    f"{B('Deploy the backend')} — a single FastAPI service; Render, Railway, or Fly all take it with uvicorn and the env vars. The in-process scheduler travels with it.",
    f"{B('Deploy the frontend')} — npm run build produces a static bundle for Vercel/Netlify; point its API proxy at the backend URL and put both behind the client's domain with HTTPS.",
    f"{B('Update Google OAuth')} — add the production callback URL to the OAuth client; submit for verification to remove the warning screen.",
    f"{B('Supabase production settings')} — Site URL set to the real domain (fixes confirmation emails); enable daily backups.",
    f"{B('Gemini billing on')} — free-tier quotas are for building, not for a client's Monday morning.",
    f"{B('Run the verification suites against production once')} — they are your acceptance test, and their green output is a deliverable you can literally show the client.",
])
story.append(Paragraph("Onboarding the client (a one-hour session)", S["h3"]))
story += steps([
    "Create their organization and accounts; each recruiter connects their Google Calendar (Settings).",
    "Configure ATS webhooks together if they have one, and send the test event while you're both watching the log.",
    "Walk one real role through the whole pipeline live: import -> rank -> approve -> send one outreach -> book one interview. The gates sell themselves.",
    "Hand over the operating manual (Chapter 5, or docs/USER_GUIDE.md in the repo) and agree on who owns the Outbox daily.",
])
story.append(Paragraph("The handoff pack", S["h3"]))
story += bullets([
    "This book, plus the in-repo README.md and docs/USER_GUIDE.md.",
    "A credentials sheet delivered through a password manager — never email or chat.",
    "The green verification-suite output from their production environment.",
    "A support agreement: what you monitor, response times, and the upgrade path (WhatsApp once Meta-verified, LinkedIn partner API if they have Recruiter, an n8n workflow layer for no-code cadence editing).",
])
story.append(Spacer(1, 4 * mm))
story.append(callout("The pitch, in one sentence", [
    "Your recruiters keep every decision that matters — the AI just makes them ten times "
    "faster at everything in between.",
], LAVENDER))

# ---- build ---------------------------------------------------------------
doc = SimpleDocTemplate(OUT, pagesize=A4, leftMargin=M, rightMargin=M,
                        topMargin=18 * mm, bottomMargin=20 * mm,
                        title="The Recruit AI Book", author="Claude for Mayank")
doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
print("written:", OUT)

