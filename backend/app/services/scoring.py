"""Gemini-based resume scoring against a job description."""
import json
import time
from functools import lru_cache

from fastapi import HTTPException

from ..config import settings

SCORE_SCHEMA = {
    "type": "object",
    "properties": {
        "full_name": {"type": "string"},
        "email": {"type": "string"},
        "phone": {"type": "string"},
        "overall_score": {"type": "number"},
        "skills_score": {"type": "number"},
        "experience_score": {"type": "number"},
        "education_score": {"type": "number"},
        "rationale": {"type": "string"},
    },
    "required": ["full_name", "overall_score", "rationale"],
}

MODEL = settings.gemini_model

PROMPT = """You are a recruitment screening assistant. Score the candidate's \
resume against the job description on a 0-100 scale (overall plus skills, \
experience, education sub-scores). Be discriminating: 90+ means an exceptional \
match, 50 means borderline, below 30 means clearly unqualified. Extract the \
candidate's full name, email, and phone from the resume if present. Keep the \
rationale to 3-4 sentences citing concrete evidence from the resume.

JOB DESCRIPTION:
{jd}

RESUME TEXT:
{resume}
"""


BATCH_SCORE_SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "overall_score": {"type": "number"},
                    "skills_score": {"type": "number"},
                    "experience_score": {"type": "number"},
                    "education_score": {"type": "number"},
                    "rationale": {"type": "string"},
                },
                "required": ["index", "overall_score", "rationale"],
            },
        }
    },
    "required": ["results"],
}

BATCH_PROMPT = """You are a recruitment screening assistant. Score EACH candidate \
profile below against the job description on a 0-100 scale (overall plus skills, \
experience, education sub-scores). Be discriminating: 90+ means an exceptional \
match, 50 means borderline, below 30 means clearly unqualified. Profiles may be \
brief sourcing summaries rather than full resumes — score on the available \
information and say so in the rationale when information is thin. Keep each \
rationale to 2-3 sentences. Return exactly one result per candidate, keyed by \
the candidate's index number.

JOB DESCRIPTION:
{jd}

CANDIDATES:
{profiles}
"""

BATCH_CHUNK_SIZE = 8

BOOLEAN_SCHEMA = {
    "type": "object",
    "properties": {
        "linkedin": {"type": "string"},
        "google_xray": {"type": "string"},
        "tips": {"type": "string"},
    },
    "required": ["linkedin", "google_xray"],
}

BOOLEAN_PROMPT = """You are a sourcing specialist. From the job description below, \
generate Boolean search strings a recruiter can paste directly into search boxes:

1. "linkedin": for LinkedIn people search — AND/OR/NOT with quoted phrases and \
parentheses, targeting titles and must-have skills. No site: operators.
2. "google_xray": a Google X-ray search of LinkedIn profiles — starts with \
site:linkedin.com/in and uses quoted phrases and -exclusions.
3. "tips": 1-2 sentences on how to tune the search (what to loosen if too few \
results, what to add if too many).

JOB DESCRIPTION:
{jd}
"""


@lru_cache
def _cached_client():
    from google import genai

    return genai.Client(api_key=settings.gemini_api_key)


def _client():
    if not settings.gemini_api_key:
        raise HTTPException(
            status_code=503,
            detail="GEMINI_API_KEY is not configured; cannot call Gemini.",
        )
    # Singleton: per-call clients can be garbage-collected mid-request,
    # closing their underlying httpx pool ("client has been closed").
    return _cached_client()


# Overloaded-model fallback: try the primary model with backoff, then the
# fallback before giving up. 429/503 are transient capacity/quota errors.
# Models are env-configurable — free-tier quotas are per-model, so flipping
# GEMINI_MODEL to the lite model keeps the app usable when flash is exhausted.
_RETRY_DELAYS = (0, 15, 30, 60)  # free tier throttles in bursts; be patient
_CHUNK_PACING_SECONDS = 6  # space out batch chunks to stay under free-tier RPM
_RETRYABLE_CODES = {429, 503}


def _generate_json(prompt: str, schema: dict) -> tuple[dict, str]:
    """Returns (parsed_json, model_that_answered)."""
    from google.genai import errors as genai_errors
    from google.genai import types

    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=schema,
    )
    last_error: Exception | None = None
    for model in (settings.gemini_model, settings.gemini_fallback_model):
        for delay in _RETRY_DELAYS:
            if delay:
                time.sleep(delay)
            try:
                resp = _client().models.generate_content(
                    model=model, contents=prompt, config=config
                )
                return json.loads(resp.text), model
            except genai_errors.APIError as e:
                if e.code in _RETRYABLE_CODES:
                    last_error = e
                    continue
                raise HTTPException(status_code=502, detail=f"Gemini error: {e}")
    raise HTTPException(
        status_code=503,
        detail=f"Gemini temporarily unavailable after retries: {last_error}",
    )


def _score_chunk(jd: str, indexed: list[tuple[int, str]], scores: list[dict | None]) -> None:
    listing = "\n".join(f"--- Candidate {i} ---\n{p[:4000]}" for i, p in indexed)
    data, model = _generate_json(
        BATCH_PROMPT.format(jd=jd[:20000], profiles=listing), BATCH_SCORE_SCHEMA
    )
    valid = {i for i, _ in indexed}
    for r in data.get("results", []):
        idx = r.get("index")
        if isinstance(idx, int) and idx in valid:
            r["model"] = model
            scores[idx] = r


def score_pool_batch(jd: str, profiles: list[str]) -> list[dict | None]:
    """Score many candidate profiles against one JD. Returns a list aligned
    with the input; entries the model failed to score come back as None."""
    scores: list[dict | None] = [None] * len(profiles)
    remaining = list(enumerate(profiles))
    # The model occasionally omits an index from a batch; sweep again over
    # just the stragglers (smaller chunks) before giving up on them.
    for attempt, chunk_size in enumerate((BATCH_CHUNK_SIZE, 4, 1)):
        if not remaining:
            break
        for start in range(0, len(remaining), chunk_size):
            if start or attempt:
                time.sleep(_CHUNK_PACING_SECONDS)
            _score_chunk(jd, remaining[start : start + chunk_size], scores)
        remaining = [(i, p) for i, p in remaining if scores[i] is None]
    return scores


def generate_boolean_search(jd: str) -> dict:
    data, _ = _generate_json(BOOLEAN_PROMPT.format(jd=jd[:20000]), BOOLEAN_SCHEMA)
    return data


def score_resume(jd: str, resume_text: str) -> dict:
    result, model = _generate_json(
        PROMPT.format(jd=jd[:20000], resume=resume_text[:40000]), SCORE_SCHEMA
    )
    result["model"] = model
    return result
