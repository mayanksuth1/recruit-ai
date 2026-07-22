"""Duplicate candidate detection: exact email match plus fuzzy name match.

Fuzzy matching is deliberately conservative — a high token-sorted similarity
alone only *flags* a possible duplicate; it merges only when corroborated by
a matching phone or current company, so two different "Rahul Sharma"s never
collapse into one record.
"""
import re
from difflib import SequenceMatcher

MERGE_THRESHOLD = 0.93   # merge (with corroboration) at/above this
FLAG_THRESHOLD = 0.85    # report as possible duplicate at/above this (review-only)


def normalize_name(name: str) -> str:
    """lowercase, strip punctuation, sort tokens — 'Mehta, Arjun' == 'arjun mehta'."""
    cleaned = re.sub(r"[^a-z\s]", " ", (name or "").lower())
    return " ".join(sorted(cleaned.split()))


def name_similarity(a: str, b: str) -> float:
    na, nb = normalize_name(a), normalize_name(b)
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


def _normalize_phone(phone: str | None) -> str:
    return re.sub(r"\D", "", phone or "")[-10:]  # last 10 digits


def find_pool_match(record: dict, pool: list[dict]) -> tuple[dict | None, str | None]:
    """Returns (existing_entry, reason) when `record` should MERGE into an
    existing pool entry, else (None, flag_message | None)."""
    email = (record.get("email") or "").lower()
    if email:
        for entry in pool:
            if (entry.get("email") or "").lower() == email:
                return entry, "email match"

    phone = _normalize_phone(record.get("phone"))
    company = (record.get("current_company") or "").strip().lower()
    best, best_score = None, 0.0
    for entry in pool:
        score = name_similarity(record.get("full_name", ""), entry.get("full_name", ""))
        if score > best_score:
            best, best_score = entry, score

    if best and best_score >= MERGE_THRESHOLD:
        same_phone = phone and _normalize_phone(best.get("phone")) == phone
        same_company = company and (best.get("current_company") or "").strip().lower() == company
        # Conflicting distinct emails on both sides → different people.
        both_emails_differ = email and best.get("email") and (best["email"].lower() != email)
        if (same_phone or same_company) and not both_emails_differ:
            return best, f"fuzzy name match ({best_score:.2f}) corroborated by " + (
                "phone" if same_phone else "company")
    if best and best_score >= FLAG_THRESHOLD:
        return None, f"possible duplicate of '{best['full_name']}' (name similarity {best_score:.2f}) — imported as new; review manually"
    return None, None


def scan_duplicates(pool: list[dict]) -> list[dict]:
    """Pairwise scan of an org's pool for likely duplicates (for review, no
    auto-merge). O(n^2) — fine at talent-pool scale."""
    suspects = []
    for i in range(len(pool)):
        for j in range(i + 1, len(pool)):
            a, b = pool[i], pool[j]
            email_match = a.get("email") and b.get("email") and a["email"].lower() == b["email"].lower()
            score = name_similarity(a.get("full_name", ""), b.get("full_name", ""))
            phone_match = _normalize_phone(a.get("phone")) and _normalize_phone(a.get("phone")) == _normalize_phone(b.get("phone"))
            if email_match or score >= FLAG_THRESHOLD or (phone_match and score >= 0.7):
                suspects.append({
                    "a": {"id": a["id"], "full_name": a["full_name"], "email": a.get("email")},
                    "b": {"id": b["id"], "full_name": b["full_name"], "email": b.get("email")},
                    "name_similarity": round(score, 3),
                    "email_match": bool(email_match),
                    "phone_match": bool(phone_match),
                })
    return suspects
