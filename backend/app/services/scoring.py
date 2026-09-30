"""Resume scoring against a job description, plus the shared model-call
engine (_generate_json) that every AI feature goes through."""
import json
import time
from functools import lru_cache

from fastapi import HTTPException

from ..config import settings
from . import ai_provider
from .ai_provider import Target

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
#
# These were tuned for Gemini's free-tier burst throttling, then shortened for
# NIM, which answers in ~1s. Still backing off, just proportionately.
_RETRY_DELAYS = (0, 2, 5, 15)
_CHUNK_PACING_SECONDS = 0.5
_RETRYABLE_CODES = {429, 503}


# One client per (endpoint, key). Per-call clients can be garbage-collected
# mid-request, closing their httpx pool, so these are kept.
_own_clients: dict[tuple[str, str], object] = {}


def _client_for(t: Target):
    if not t.own:
        return _client()
    key = (t.base_url, t.api_key)
    client = _own_clients.get(key)
    if client is None:
        from openai import OpenAI

        if len(_own_clients) > 200:
            _own_clients.clear()
        client = _own_clients[key] = OpenAI(
            api_key=t.api_key, base_url=t.base_url,
            # Redirects stay off (httpx default), so a custom endpoint cannot
            # bounce the request to an internal address after the URL check.
            timeout=300.0, max_retries=0,
        )
    return client


# How to ask for JSON, strictest first. Providers differ: NIM and OpenAI
# enforce a json_schema; some only take json_object; Anthropic's compatibility
# layer ignores response_format entirely. The mode that last worked for an
# (endpoint, model) pair is remembered so later calls start there.
_MODES = ("json_schema", "json_object", "prompt")
_quirks: dict[tuple[str, str], dict] = {}


class _BadOutput(Exception):
    """The model answered, but not with JSON matching the schema."""


def _schema_instruction(schema: dict) -> str:
    return (
        "\n\nReply with ONLY a single JSON object that matches this JSON Schema. "
        "No prose before or after it, no markdown code fences.\nJSON Schema:\n"
        + json.dumps(schema)
    )


def _parse_json(content: str, schema: dict) -> dict:
    import jsonschema

    text = content.strip()
    try:
        data = json.loads(text)
    except ValueError:
        # Fenced or chatty output: take the outermost object.
        i, j = text.find("{"), text.rfind("}")
        if i < 0 or j <= i:
            raise _BadOutput("no JSON object in the reply")
        try:
            data = json.loads(text[i : j + 1])
        except ValueError as e:
            raise _BadOutput(f"unparseable JSON: {e}")
    try:
        jsonschema.validate(data, schema)
    except jsonschema.ValidationError as e:
        raise _BadOutput(f"JSON did not match the expected shape: {e.message}")
    return data


def _call_once(client, t: Target, model: str, prompt: str, schema: dict) -> dict:
    import openai

    q = _quirks.setdefault((t.base_url, model),
                           {"mode": 0, "max_completion_tokens": False, "no_temperature": False})
    last: Exception | None = None
    for mode_idx in range(q["mode"], len(_MODES)):
        mode = _MODES[mode_idx]
        text = prompt if mode == "json_schema" else prompt + _schema_instruction(schema)
        for _ in range(3):  # room to adapt parameters the endpoint rejects
            kwargs: dict = {"model": model, "messages": [{"role": "user", "content": text}]}
            # Newer OpenAI reasoning models reject max_tokens and any
            # temperature other than the default; learn that once.
            kwargs["max_completion_tokens" if q["max_completion_tokens"] else "max_tokens"] = 4096
            if not q["no_temperature"]:
                kwargs["temperature"] = 0.4
            if mode == "json_schema":
                kwargs["response_format"] = {
                    "type": "json_schema", "json_schema": {"name": "response", "schema": schema},
                }
            elif mode == "json_object":
                kwargs["response_format"] = {"type": "json_object"}
            try:
                resp = client.chat.completions.create(**kwargs)
            except openai.BadRequestError as e:
                msg = str(e).lower()
                if "max_tokens" in msg and not q["max_completion_tokens"]:
                    q["max_completion_tokens"] = True
                    continue
                if "temperature" in msg and not q["no_temperature"]:
                    q["no_temperature"] = True
                    continue
                if mode == "prompt":
                    raise
                last = e
                break  # a simpler way of asking for JSON may be accepted
            content = resp.choices[0].message.content if resp.choices else None
            if not content:
                # Reasoning-style models can leave `content` null.
                last = _BadOutput(f"{model} returned no text")
                break
            try:
                data = _parse_json(content, schema)
            except _BadOutput as e:
                last = e
                break
            q["mode"] = mode_idx
            return data
    if isinstance(last, openai.BadRequestError):
        raise last
    raise _BadOutput(str(last) if last else "no usable answer")


def _generate_with_target(t: Target, prompt: str, schema: dict, quality: bool) -> tuple[dict, str]:
    """(parsed_json, model_that_answered) from this target, with retries and
    errors worded for whoever has to fix them."""
    import openai

    who = t.label if t.own else "The AI service"
    fix = " Update it in Settings → AI provider." if t.own else ""
    client = _client_for(t)
    # dict.fromkeys keeps order while dropping a duplicate fallback, so a
    # failure is not retried against the same model twice for no reason.
    candidates = list(dict.fromkeys([t.quality_model if quality else t.model, t.fallback_model]))
    last_error: Exception | None = None
    for model in candidates:
        for delay in _RETRY_DELAYS:
            if delay:
                time.sleep(delay)
            try:
                return _call_once(client, t, model, prompt, schema), model
            except openai.RateLimitError as e:
                if "insufficient_quota" in str(e) or "credit" in str(e).lower():
                    raise HTTPException(status_code=402, detail=f"Your {who} account has no credit left.{fix}")
                last_error = e
            except (openai.APITimeoutError, openai.APIConnectionError) as e:
                last_error = e
            except (openai.AuthenticationError, openai.PermissionDeniedError):
                if t.own:
                    raise HTTPException(status_code=400, detail=f"{who} rejected your API key.{fix}")
                raise HTTPException(status_code=502, detail="The platform AI key was rejected.")
            except openai.NotFoundError:
                if t.own:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Model '{model}' was not found at {who}. Choose another in Settings → AI provider.",
                    )
                raise HTTPException(status_code=502, detail=f"Platform model {model} is unavailable.")
            except openai.APIStatusError as e:
                if e.status_code in _RETRYABLE_CODES:
                    last_error = e
                    continue
                raise HTTPException(status_code=502, detail=f"{who} error: {str(e)[:300]}")
            except _BadOutput as e:
                last_error = e
                break  # same prompt, same model: try the fallback instead
    if isinstance(last_error, _BadOutput):
        raise HTTPException(
            status_code=502,
            detail=f"{who} did not return a usable answer ({last_error}). A larger model usually fixes this.{fix}",
        )
    raise HTTPException(status_code=503, detail=f"{who} is temporarily unavailable after retries: {last_error}")


def _generate_json(prompt: str, schema: dict, *, org_id: str | None,
                   quality: bool = False, candidate_facing: bool = False) -> tuple[dict, str]:
    """Returns (parsed_json, model_that_answered) using the organization's own
    provider, or the platform key within the free monthly allowance.

    `quality` opts a call site into the provider's stronger model: output that
    is written once, read carefully by a human and expensive to get wrong (the
    LinkedIn post, interview transcript scoring). `candidate_facing` marks a
    call a candidate is waiting on, which the allowance never cuts off.
    """
    t = ai_provider.resolve(org_id)
    if not t.own:
        ai_provider.meter_platform_call(org_id, candidate_facing=candidate_facing)
    return _generate_with_target(t, prompt, schema, quality)


_PING_SCHEMA = {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]}


def test_target(t: Target) -> dict:
    """One tiny structured call per model, used before a provider is saved."""
    started = time.monotonic()
    _, model = _generate_with_target(t, 'Reply with {"ok": true}.', _PING_SCHEMA, quality=False)
    if t.quality_model != t.model:
        _generate_with_target(t, 'Reply with {"ok": true}.', _PING_SCHEMA, quality=True)
    return {"model": model, "seconds": round(time.monotonic() - started, 1)}


def list_models(t: Target) -> list[str]:
    import openai

    try:
        ids = [m.id for m in _client_for(t).models.list()]
    except (openai.AuthenticationError, openai.PermissionDeniedError):
        raise HTTPException(status_code=400, detail=f"{t.label} rejected this API key.")
    except openai.APIError as e:
        raise HTTPException(
            status_code=502,
            detail=f"{t.label} would not list its models ({str(e)[:200]}). Type the model name instead.",
        )
    return sorted(set(ids))[:1000]


def _score_chunk(jd: str, indexed: list[tuple[int, str]], scores: list[dict | None],
                 org_id: str | None) -> None:
    listing = "\n".join(f"--- Candidate {i} ---\n{p[:4000]}" for i, p in indexed)
    data, model = _generate_json(
        BATCH_PROMPT.format(jd=jd[:20000], profiles=listing), BATCH_SCORE_SCHEMA, org_id=org_id
    )
    valid = {i for i, _ in indexed}
    for r in data.get("results", []):
        idx = r.get("index")
        if isinstance(idx, int) and idx in valid:
            r["model"] = model
            scores[idx] = r


def score_pool_batch(jd: str, profiles: list[str], *, org_id: str | None) -> list[dict | None]:
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
            _score_chunk(jd, remaining[start : start + chunk_size], scores, org_id)
        remaining = [(i, p) for i, p in remaining if scores[i] is None]
    return scores


def generate_boolean_search(jd: str, *, org_id: str | None) -> dict:
    data, _ = _generate_json(BOOLEAN_PROMPT.format(jd=jd[:20000]), BOOLEAN_SCHEMA, org_id=org_id)
    return data


def score_resume(jd: str, resume_text: str, *, org_id: str | None) -> dict:
    result, model = _generate_json(
        PROMPT.format(jd=jd[:20000], resume=resume_text[:40000]), SCORE_SCHEMA, org_id=org_id
    )
    result["model"] = model
    return result
