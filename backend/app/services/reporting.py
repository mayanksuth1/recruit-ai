"""Funnel metrics + weekly summaries.

Funnel stage definitions (an org-wide candidate can satisfy several):
  sourced      any candidate record
  screened     has at least one score
  outreached   has at least one SENT outreach email
  interviewed  has an interview with a scheduled time (not cancelled)
  offered      stage is 'offer' or 'closed' (passed gate 2)
  closed       stage is 'closed'

The metrics payload is PII-free by construction (counts and role titles
only) — the recruiter endpoint layers names on top separately, so the
client-facing view and PDF can safely reuse the base payload.
"""
from datetime import date, datetime, timedelta, timezone

from ..db import service_client

FUNNEL_STAGES = ["sourced", "screened", "outreached", "interviewed", "offered", "closed"]


def build_metrics(org_id: str, role_id: str | None = None) -> dict:
    db = service_client()
    cq = db.table("candidates").select("id, role_id, stage, shortlist_status").eq("organization_id", org_id)
    if role_id:
        cq = cq.eq("role_id", role_id)
    cands = cq.execute().data
    ids = {c["id"] for c in cands}

    scores = db.table("scores").select("candidate_id, overall_score").eq("organization_id", org_id).execute().data
    scores = [s for s in scores if s["candidate_id"] in ids]
    scored_ids = {s["candidate_id"] for s in scores}

    sent_outreach = (
        db.table("messages").select("candidate_id")
        .eq("organization_id", org_id).eq("kind", "outreach").eq("status", "sent")
        .execute().data
    )
    outreached_ids = {m["candidate_id"] for m in sent_outreach if m["candidate_id"] in ids}

    interviews = (
        db.table("interviews").select("candidate_id, scheduled_start, status")
        .eq("organization_id", org_id).execute().data
    )
    interviewed_ids = {
        i["candidate_id"] for i in interviews
        if i["candidate_id"] in ids and i.get("scheduled_start") and i["status"] != "cancelled"
    }

    stage_sets = {
        "sourced": ids,
        "screened": scored_ids,
        "outreached": outreached_ids,
        "interviewed": interviewed_ids,
        "offered": {c["id"] for c in cands if c["stage"] in ("offer", "closed")},
        "closed": {c["id"] for c in cands if c["stage"] == "closed"},
    }

    funnel = []
    for i, stage in enumerate(FUNNEL_STAGES):
        count = len(stage_sets[stage])
        prev_count = len(stage_sets[FUNNEL_STAGES[i - 1]]) if i else None
        drop_off = (
            round((1 - count / prev_count) * 100, 1) if prev_count else None
        ) if i else None
        funnel.append({"stage": stage, "count": count, "drop_off_pct": drop_off})

    roles = db.table("roles").select("id, title").eq("organization_id", org_id).execute().data
    titles = {r["id"]: r["title"] for r in roles}
    per_role = []
    for rid, title in titles.items():
        role_ids = {c["id"] for c in cands if c["role_id"] == rid}
        if not role_ids and role_id is None:
            per_role.append({"role_title": title, **{s: 0 for s in FUNNEL_STAGES}})
            continue
        per_role.append({
            "role_title": title,
            **{s: len(stage_sets[s] & role_ids) for s in FUNNEL_STAGES},
        })

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "funnel": funnel,
        "per_role": per_role,
        "totals": {
            "candidates": len(ids),
            "shortlist_approved": sum(1 for c in cands if c["shortlist_status"] == "approved"),
            "avg_score": round(sum(s["overall_score"] for s in scores) / len(scores), 1) if scores else None,
        },
    }


def recruiter_extras(org_id: str) -> dict:
    """Detail layer for the internal view only — contains candidate names."""
    db = service_client()
    now = datetime.now(timezone.utc)
    upcoming = (
        db.table("interviews").select("scheduled_start, duration_minutes, candidates(full_name), roles(title)")
        .eq("organization_id", org_id).eq("status", "scheduled")
        .gte("scheduled_start", now.isoformat())
        .order("scheduled_start").limit(10)
        .execute().data
    )
    drafts = (
        db.table("messages").select("id", count="exact")
        .eq("organization_id", org_id).eq("status", "draft")
        .execute()
    )
    return {
        "upcoming_interviews": [
            {"candidate": u["candidates"]["full_name"] if u.get("candidates") else "?",
             "role": (u.get("roles") or {}).get("title"),
             "start": u["scheduled_start"], "duration_minutes": u["duration_minutes"]}
            for u in upcoming
        ],
        "pending_drafts": drafts.count or 0,
    }


def _week_bounds(today: date) -> tuple[date, date]:
    start = today - timedelta(days=today.weekday())  # Monday
    return start, start + timedelta(days=6)


def generate_weekly_reports() -> int:
    """Create this week's summary for every org with candidates that doesn't
    have one yet. Stored only — never auto-emailed."""
    db = service_client()
    start, end = _week_bounds(datetime.now(timezone.utc).date())
    orgs = db.table("organizations").select("id, name").execute().data
    created = 0
    for org in orgs:
        has_cands = (
            db.table("candidates").select("id", count="exact")
            .eq("organization_id", org["id"]).limit(1).execute().count
        )
        if not has_cands:
            continue
        existing = (
            db.table("reports").select("id")
            .eq("organization_id", org["id"]).eq("kind", "weekly")
            .eq("period_start", start.isoformat())
            .execute().data
        )
        if existing:
            continue
        db.table("reports").insert({
            "organization_id": org["id"],
            "kind": "weekly",
            "period_start": start.isoformat(),
            "period_end": end.isoformat(),
            "data": {"org_name": org["name"], **build_metrics(org["id"])},
        }).execute()
        created += 1
    return created


def render_pdf(report: dict) -> bytes:
    """Render a stored report to PDF (fpdf2). Pastel-themed to match the app."""
    from fpdf import FPDF

    data = report["data"]
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()

    pdf.set_fill_color(248, 200, 176)  # peach band
    pdf.rect(0, 0, 210, 26, "F")
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(92, 80, 73)
    pdf.set_xy(10, 8)
    pdf.cell(0, 10, f"{data.get('org_name', 'Recruitment')} - Weekly Summary")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_xy(10, 30)
    pdf.cell(0, 6, f"Week {report['period_start']} to {report['period_end']}  |  "
                   f"generated {str(data.get('generated_at', ''))[:10]}")

    pdf.set_xy(10, 42)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Hiring funnel")
    pdf.ln(10)
    pdf.set_font("Helvetica", "", 10)
    max_count = max((f["count"] for f in data["funnel"]), default=0) or 1
    bar_colors = [(248, 200, 176), (247, 223, 174), (191, 230, 221),
                  (188, 217, 238), (199, 197, 238), (243, 184, 195)]
    for i, f in enumerate(data["funnel"]):
        y = pdf.get_y()
        pdf.set_x(12)
        pdf.cell(28, 7, f["stage"].capitalize())
        width = 100 * f["count"] / max_count
        pdf.set_fill_color(*bar_colors[i % len(bar_colors)])
        pdf.rect(42, y + 1, max(width, 1.5), 5, "F")
        pdf.set_x(145)
        drop = f" (drop-off {f['drop_off_pct']}%)" if f.get("drop_off_pct") is not None else ""
        pdf.cell(0, 7, f"{f['count']}{drop}")
        pdf.ln(7)

    totals = data.get("totals", {})
    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(0, 8, "Totals")
    pdf.ln(9)
    pdf.set_font("Helvetica", "", 10)
    pdf.set_x(12)
    avg = totals.get("avg_score")
    pdf.multi_cell(0, 6,
                   f"Candidates: {totals.get('candidates', 0)}   |   "
                   f"Shortlist approved: {totals.get('shortlist_approved', 0)}   |   "
                   f"Average match score: {avg if avg is not None else 'n/a'}")

    if data.get("per_role"):
        pdf.ln(4)
        pdf.set_font("Helvetica", "B", 12)
        pdf.cell(0, 8, "By role")
        pdf.ln(9)
        pdf.set_font("Helvetica", "B", 9)
        headers = ["Role", "Sourced", "Screened", "Outreached", "Interviewed", "Offered", "Closed"]
        widths = [60, 22, 22, 24, 25, 20, 17]
        pdf.set_x(12)
        for h, w in zip(headers, widths):
            pdf.cell(w, 7, h, border="B")
        pdf.ln(7)
        pdf.set_font("Helvetica", "", 9)
        for row in data["per_role"]:
            pdf.set_x(12)
            pdf.cell(widths[0], 7, str(row["role_title"])[:38])
            for key, w in zip(FUNNEL_STAGES, widths[1:]):
                pdf.cell(w, 7, str(row.get(key, 0)))
            pdf.ln(7)

    pdf.set_y(-24)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(150, 140, 132)
    pdf.cell(0, 6, "Generated by Recruit AI - contains aggregate data only, no candidate PII.")
    return bytes(pdf.output())
