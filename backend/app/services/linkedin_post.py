"""Gemini-drafted LinkedIn job posts. Draft only — there is no publishing step.

The output is plain text the recruiter copies and posts themselves. This module
deliberately has no LinkedIn client, no OAuth and no image generation; it takes
the company profile plus a role's job description and returns copy.
"""
from ..config import settings
from .scoring import _generate_json

# Hashtags come back as a separate array rather than baked into `post` so the
# model cannot bury them mid-paragraph; the caller joins them onto the end.
LINKEDIN_POST_SCHEMA = {
    "type": "object",
    "properties": {
        "post": {"type": "string"},
        "hashtags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["post"],
}

POST_PROMPT = """Write a LinkedIn job post advertising the role below, on behalf of
the company described below.

Rules:
- Plain text only. No markdown, no HTML, no bullet characters other than "-".
- 120-220 words. Open with a hook line, not "We are hiring".
- Ground the post in BOTH inputs. Reference at least two specifics from the job
  description (actual responsibilities, must-have skills or seniority) and at
  least two specifics from the company profile (what the company does, culture,
  benefits or location). Generic filler that would fit any company is a failure.
- Never invent facts. No salary figures, headcount, funding, perks or claims that
  are not present in the inputs. If the company profile is thin, write a shorter
  post rather than padding it with invention.
- End with a clear, low-friction call to action to apply or get in touch.
- Do not write hashtags inside "post" — put them in the "hashtags" array, without
  the leading '#', 3 to 6 of them, relevant to the role and industry.

COMPANY PROFILE:
Company name: {company_name}
What the company does: {what_we_do}
Culture and benefits: {culture_benefits}
Location: {location}
Anything else worth telling candidates: {extra_notes}

ROLE TITLE:
{role_title}

ROLE JOB DESCRIPTION:
{jd}
"""


def _clean(value: str | None, fallback: str = "(not provided)") -> str:
    text = (value or "").strip()
    return text or fallback


def generate_linkedin_post(profile: dict, role_title: str, jd: str) -> tuple[str, str]:
    """Returns (post_text, model_that_answered).

    `post_text` is the finished, copy-ready draft: the body with the hashtag
    line appended. The caller stores it verbatim so what the user sees, edits
    and copies is exactly what was persisted.
    """
    prompt = POST_PROMPT.format(
        company_name=_clean(profile.get("company_name")),
        what_we_do=_clean(profile.get("what_we_do")),
        culture_benefits=_clean(profile.get("culture_benefits")),
        location=_clean(profile.get("location")),
        extra_notes=_clean(profile.get("extra_notes"), "(nothing further)"),
        role_title=_clean(role_title, "(untitled role)"),
        jd=jd[:20000],
    )
    # Quality model: a job post is written once per role, read by a human before
    # it goes anywhere, and is the most public thing this app produces — worth
    # the slower call in a way that per-candidate scoring is not.
    data, model = _generate_json(
        prompt, LINKEDIN_POST_SCHEMA, model=settings.nvidia_quality_model
    )

    post = (data.get("post") or "").strip()
    tags = [t.strip().lstrip("#") for t in (data.get("hashtags") or []) if t and t.strip()]
    if tags:
        post = f"{post}\n\n" + " ".join(f"#{t}" for t in tags)
    return post, model
