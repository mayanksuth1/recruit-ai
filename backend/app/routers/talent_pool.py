from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from ..auth import CurrentUser, require_org
from ..db import service_client
from ..services.csv_import import parse_candidates_csv
from ..services.dedupe import find_pool_match, scan_duplicates

router = APIRouter(prefix="/api/talent-pool", tags=["talent-pool"])

POOL_FIELDS = (
    "full_name", "email", "phone", "location", "current_title",
    "current_company", "years_experience", "skills", "profile_text",
)


@router.get("")
def list_pool(user: CurrentUser = Depends(require_org)):
    return (
        service_client()
        .table("talent_pool")
        .select("*")
        .eq("organization_id", user.organization_id)
        .order("created_at", desc=True)
        .limit(500)
        .execute()
        .data
    )


@router.post("/import")
async def import_candidates(
    file: UploadFile | None = File(None),
    csv_text: str | None = Form(None),
    user: CurrentUser = Depends(require_org),
):
    """Import candidates from an uploaded CSV file or pasted CSV text.
    Rows matching an existing pool entry by email (same org) are updated,
    not duplicated."""
    if file is not None:
        raw = await file.read()
        if len(raw) > 5 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="CSV larger than 5 MB")
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("latin-1")
        source = "csv_import"
    elif csv_text and csv_text.strip():
        text = csv_text
        source = "paste_import"
    else:
        raise HTTPException(status_code=400, detail="Provide a CSV file or pasted CSV text")

    rows, warnings = parse_candidates_csv(text)
    if not rows:
        raise HTTPException(status_code=400, detail="; ".join(warnings) or "No candidates found in CSV")

    db = service_client()
    pool = (
        db.table("talent_pool")
        .select("id, full_name, email, phone, current_company")
        .eq("organization_id", user.organization_id)
        .execute()
        .data
    )

    inserted, updated = 0, 0
    seen_emails: set[str] = set()
    for row in rows:
        record = {k: row.get(k) for k in POOL_FIELDS if row.get(k) is not None}
        email = record.get("email")
        if email and email in seen_emails:
            warnings.append(f"Duplicate email within import skipped: {email}")
            continue
        if email:
            seen_emails.add(email)

        # Duplicate detection: exact email, or fuzzy name corroborated by
        # phone/company (conservative — see services/dedupe.py).
        match, note = find_pool_match(record, pool)
        if match:
            db.table("talent_pool").update(record).eq("id", match["id"]).execute()
            match.update({k: record.get(k, match.get(k)) for k in ("full_name", "email", "phone", "current_company")})
            if note != "email match":
                warnings.append(f"'{record.get('full_name')}' merged into existing '{match['full_name']}' ({note})")
            updated += 1
        else:
            if note:
                warnings.append(note)
            record["organization_id"] = user.organization_id
            record["source"] = source
            new_row = db.table("talent_pool").insert(record).execute().data[0]
            pool.append({k: new_row.get(k) for k in ("id", "full_name", "email", "phone", "current_company")})
            inserted += 1

    return {"inserted": inserted, "updated": updated, "warnings": warnings}


@router.get("/duplicates")
def list_duplicates(user: CurrentUser = Depends(require_org)):
    """Pairwise duplicate scan of the org's talent pool (review only — no
    automatic merging of existing records)."""
    pool = (
        service_client().table("talent_pool")
        .select("id, full_name, email, phone")
        .eq("organization_id", user.organization_id)
        .limit(500)
        .execute().data
    )
    return {"pairs": scan_duplicates(pool)}
