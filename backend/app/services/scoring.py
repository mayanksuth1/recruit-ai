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
    from openai import OpenAI

    # NVIDIA NIM is OpenAI-API-compatible; only the base URL differs.
    return OpenAI(
        api_key=settings.nvidia_api_key,
        base_url=settings.nvidia_base_url,
        # Generous because glm-5.2 answers in minutes, not seconds: a long
        # generation can run well past the old 180s and a timeout here would
        # throw away a nearly-finished response and pay the whole cost again.
        timeout=900.0,
        max_retries=0,  # retries/backoff are handled below so both models get a turn
    )


def _client():
    if not settings.nvidia_api_key:
        raise HTTPException(
            status_code=503,
            detail="NVIDIA_API_KEY is not configured; cannot call the model.",
        )
    # Singleton: per-call clients can be garbage-collected mid-request,
    # closing their underlying httpx pool ("client has been closed").
    return _cached_client()


# Overloaded-model fallback: try the primary model with backoff, then the
# fallback before giving up. 429/503 are transient capacity/quota errors.
# Models are env-configurable via NVIDIA_MODEL / NVIDIA_FALLBACK_MODEL.
#
# These two were tuned for Gemini's free-tier burst throttling, where waiting
# was cheaper than retrying. NIM answers in ~1s, so the old values dominated
# every batch: 6s between chunks meant scoring 40 candidates spent ~30s asleep,
# and a failing call could sit in backoff for 105s per model before surfacing.
# Shortened to match the new provider — still backing off, just proportionately.
_RETRY_DELAYS = (0, 2, 5, 15)
_CHUNK_PACING_SECONDS = 0.5
_RETRYABLE_CODES = {429, 503}


def _generate_json(prompt: str, schema: dict, model: str | None = None) -> tuple[dict, str]:
    """Returns (parsed_json, model_that_answered).

    Structured output uses OpenAI-style `response_format: json_schema`, which
    NIM applies as guided decoding — the model cannot emit anything the schema
    rejects, so json.loads() below is safe without a repair pass.

    `model` opts a single call site into a different model than the default —
    see settings.nvidia_quality_model. The fallback is always the configured
    fast one, so a slow-model outage degrades to a quick answer rather than to
    a second long wait.
    """
    import openai

    response_format = {
        "type": "json_schema",
        "json_schema": {"name": "response", "schema": schema},
    }
    # dict.fromkeys keeps order while dropping the duplicate when the chosen
    # model already is the fallback — otherwise every failure would be retried
    # against the same model twice for no reason.
    candidates = list(dict.fromkeys([model or settings.nvidia_model,
                                     settings.nvidia_fallback_model]))
    last_error: Exception | None = None
    for model in candidates:
        for delay in _RETRY_DELAYS:
            if delay:
                time.sleep(delay)
            try:
                resp = _client().chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.4,
                    max_tokens=4096,
                    response_format=response_format,
                )
                content = resp.choices[0].message.content
                if not content:
                    # Reasoning-style models put their answer in
                    # `reasoning_content` and leave `content` null. Treat it as
                    # a bad model choice rather than retrying the same way.
                    raise HTTPException(
                        status_code=502,
                        detail=f"{model} returned no content; it is not usable for JSON output.",
                    )
                return json.loads(content), model
            except (openai.RateLimitError, openai.APITimeoutError, openai.APIConnectionError) as e:
                last_error = e
                continue
            except openai.APIStatusError as e:
                if e.status_code in _RETRYABLE_CODES:
                    last_error = e
                    continue
                raise HTTPException(status_code=502, detail=f"NVIDIA NIM error: {e}")
    raise HTTPException(
        status_code=503,
        detail=f"NVIDIA NIM temporarily unavailable after retries: {last_error}",
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
