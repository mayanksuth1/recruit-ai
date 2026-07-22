from fastapi import APIRouter, Depends, HTTPException, Response

from ..auth import CurrentUser, require_org
from ..db import service_client
from ..services import reporting

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/funnel")
def funnel(role_id: str | None = None, user: CurrentUser = Depends(require_org)):
    """Internal recruiter view: full metrics plus name-level detail."""
    metrics = reporting.build_metrics(user.organization_id, role_id)
    return {**metrics, **reporting.recruiter_extras(user.organization_id)}


@router.get("/client-summary")
def client_summary(user: CurrentUser = Depends(require_org)):
    """Client-facing view: aggregate counts and role titles only — no
    candidate names, emails, or any other PII."""
    db = service_client()
    org = db.table("organizations").select("name").eq("id", user.organization_id).single().execute().data
    return {"org_name": org["name"], **reporting.build_metrics(user.organization_id)}


@router.post("/generate", status_code=201)
def generate_now(user: CurrentUser = Depends(require_org)):
    """Create (or return) this week's stored summary for the org."""
    created = _generate_for_org(user.organization_id)
    reports = _list_reports(user.organization_id)
    return {"created": created, "latest": reports[0] if reports else None}


def _generate_for_org(org_id: str) -> bool:
    from datetime import datetime, timezone

    db = service_client()
    start, end = reporting._week_bounds(datetime.now(timezone.utc).date())
    existing = (
        db.table("reports").select("id")
        .eq("organization_id", org_id).eq("kind", "weekly")
        .eq("period_start", start.isoformat())
        .execute().data
    )
    if existing:
        return False
    org = db.table("organizations").select("name").eq("id", org_id).single().execute().data
    db.table("reports").insert({
        "organization_id": org_id,
        "kind": "weekly",
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "data": {"org_name": org["name"], **reporting.build_metrics(org_id)},
    }).execute()
    return True


def _list_reports(org_id: str) -> list[dict]:
    return (
        service_client().table("reports")
        .select("id, kind, period_start, period_end, created_at")
        .eq("organization_id", org_id)
        .order("period_start", desc=True).limit(52)
        .execute().data
    )


@router.get("")
def list_reports(user: CurrentUser = Depends(require_org)):
    return _list_reports(user.organization_id)


@router.get("/{report_id}/pdf")
def download_pdf(report_id: str, user: CurrentUser = Depends(require_org)):
    rows = (
        service_client().table("reports").select("*")
        .eq("id", report_id).eq("organization_id", user.organization_id)
        .execute().data
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Report not found")
    report = rows[0]
    pdf_bytes = reporting.render_pdf(report)
    filename = f"weekly-summary-{report['period_start']}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
