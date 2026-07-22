"""Gemini-drafted candidate emails. Drafts only — sending is a separate,
explicitly human-triggered step."""
from .scoring import _generate_json

EMAIL_SCHEMA = {
    "type": "object",
    "properties": {
        "subject": {"type": "string"},
        "body": {"type": "string"},
    },
    "required": ["subject", "body"],
}

_COMMON_RULES = """Rules:
- Plain text only, no markdown or HTML.
- Concise (under 160 words), warm but professional.
- Never invent facts: no salary numbers, benefits, company claims, or details
  not present in the inputs. If something is unknown, leave it out.
- Do not promise timelines or outcomes.
- Sign off with the sender name exactly as given.
"""

OUTREACH_PROMPT = """Write a personalized first-contact recruiting email to a candidate.
Reference 1-2 specific things from their profile that make them a fit for the role.
Invite them to reply if interested.

{rules}
ROLE ({role_title}) JOB DESCRIPTION:
{jd}

CANDIDATE PROFILE ({candidate_name}):
{profile}

SENDER: {sender_name} at {org_name}
"""

STATUS_UPDATE_PROMPT = """Write a brief status-update email to a candidate about their
application. Their application for the role has moved to the "{new_stage}" stage.
Explain what that means neutrally in one sentence (no promises about outcomes).

{rules}
ROLE: {role_title} at {org_name}
CANDIDATE: {candidate_name}
SENDER: {sender_name} at {org_name}
"""

FOLLOW_UP_PROMPT = """Write a short, polite follow-up email to a candidate who has not
replied to the earlier outreach email below. Reference it lightly, add one new reason
the role could interest them, and make replying easy. Do not guilt-trip.

{rules}
ROLE ({role_title}) JOB DESCRIPTION:
{jd}

CANDIDATE PROFILE ({candidate_name}):
{profile}

EARLIER EMAIL (sent {days_ago} days ago):
Subject: {prev_subject}
{prev_body}

SENDER: {sender_name} at {org_name}
"""


def draft_outreach(role_title: str, jd: str, candidate_name: str, profile: str,
                   sender_name: str, org_name: str) -> dict:
    data, model = _generate_json(
        OUTREACH_PROMPT.format(
            rules=_COMMON_RULES, role_title=role_title, jd=jd[:20000],
            candidate_name=candidate_name, profile=(profile or "")[:20000],
            sender_name=sender_name, org_name=org_name,
        ),
        EMAIL_SCHEMA,
    )
    data["model"] = model
    return data


def draft_status_update(role_title: str, new_stage: str, candidate_name: str,
                        sender_name: str, org_name: str) -> dict:
    data, model = _generate_json(
        STATUS_UPDATE_PROMPT.format(
            rules=_COMMON_RULES, role_title=role_title, new_stage=new_stage,
            candidate_name=candidate_name, sender_name=sender_name, org_name=org_name,
        ),
        EMAIL_SCHEMA,
    )
    data["model"] = model
    return data


def draft_follow_up(role_title: str, jd: str, candidate_name: str, profile: str,
                    prev_subject: str, prev_body: str, days_ago: int,
                    sender_name: str, org_name: str) -> dict:
    data, model = _generate_json(
        FOLLOW_UP_PROMPT.format(
            rules=_COMMON_RULES, role_title=role_title, jd=jd[:20000],
            candidate_name=candidate_name, profile=(profile or "")[:20000],
            prev_subject=prev_subject, prev_body=prev_body[:5000], days_ago=days_ago,
            sender_name=sender_name, org_name=org_name,
        ),
        EMAIL_SCHEMA,
    )
    data["model"] = model
    return data
