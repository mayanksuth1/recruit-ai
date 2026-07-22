"""Flexible CSV parsing for candidate imports (e.g. exported search results).

Maps common header variants onto talent_pool fields; unknown columns are
folded into profile_text so no information is silently dropped.
"""
import csv
import io

FIELD_ALIASES = {
    "full_name": {"name", "full name", "full_name", "candidate name", "candidate"},
    "email": {"email", "email address", "e-mail", "e mail"},
    "phone": {"phone", "phone number", "mobile", "contact", "contact number"},
    "current_title": {"title", "current title", "job title", "headline", "position", "role", "designation"},
    "current_company": {"company", "current company", "employer", "organisation", "organization"},
    "location": {"location", "city", "region", "country"},
    "years_experience": {"years experience", "years_experience", "years of experience", "experience", "years", "yoe", "exp"},
    "skills": {"skills", "skill", "keywords", "key skills", "technologies"},
    "summary": {"summary", "notes", "profile", "about", "description", "bio"},
}


def _normalize(header: str) -> str:
    return header.strip().lower().replace("_", " ").replace("-", " ")


def _map_headers(headers: list[str]) -> dict[int, str]:
    """column index -> canonical field name ('' = unmapped extra column)."""
    mapping = {}
    for i, h in enumerate(headers):
        norm = _normalize(h)
        for field, aliases in FIELD_ALIASES.items():
            if norm in aliases or norm.replace(" ", "_") in aliases:
                mapping[i] = field
                break
        else:
            mapping[i] = ""
    return mapping


def parse_candidates_csv(text: str) -> tuple[list[dict], list[str]]:
    """Returns (rows, warnings). Each row has talent_pool-shaped keys."""
    text = text.lstrip("﻿")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    rows = list(reader)
    if len(rows) < 2:
        return [], ["CSV needs a header row and at least one data row"]

    headers = rows[0]
    mapping = _map_headers(headers)
    if "full_name" not in mapping.values():
        return [], [f"No name column found (headers: {', '.join(headers)})"]

    parsed, warnings = [], []
    for line_no, raw in enumerate(rows[1:], start=2):
        if not any(cell.strip() for cell in raw):
            continue
        record: dict = {}
        extras: list[str] = []
        for i, cell in enumerate(raw):
            cell = cell.strip()
            if not cell or i >= len(headers):
                continue
            field = mapping.get(i, "")
            if field == "":
                extras.append(f"{headers[i].strip()}: {cell}")
            elif field == "years_experience":
                digits = "".join(ch for ch in cell if ch.isdigit() or ch == ".")
                try:
                    record[field] = float(digits)
                except ValueError:
                    extras.append(f"{headers[i].strip()}: {cell}")
            else:
                record[field] = cell

        if not record.get("full_name"):
            warnings.append(f"Line {line_no}: skipped (no name)")
            continue
        if record.get("email"):
            record["email"] = record["email"].lower()

        summary = record.pop("summary", "")
        profile_parts = [
            " at ".join(p for p in (record.get("current_title"), record.get("current_company")) if p),
            f"Location: {record['location']}" if record.get("location") else "",
            f"Experience: {record['years_experience']:g} years" if record.get("years_experience") is not None else "",
            f"Skills: {record['skills']}" if record.get("skills") else "",
            summary,
            *extras,
        ]
        record["profile_text"] = "\n".join(p for p in profile_parts if p)
        parsed.append(record)

    return parsed, warnings
