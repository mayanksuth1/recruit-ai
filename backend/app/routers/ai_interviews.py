"""Asynchronous AI interviews — issuing links, running them, scoring them,
and semantic search over what they produced (Level 2).

The candidate is unauthenticated. They hold a single-use token, not a JWT, so
every candidate-side read and write runs through the service role keyed by that
token — the same posture as the existing /api/public/schedule/{token} pages.
`ai_interview_sessions` and `ai_interview_turns` have SELECT-only RLS policies
precisely so that no recruiter JWT can write a candidate's answer.

The ordering rule this module exists to uphold: THE QUESTION IS PERSISTED
BEFORE IT IS SHOWN. Generate, insert, then serve — never serve then insert. A
tab closed in between must find the question already on record so it is
re-served verbatim, rather than a fresh one being generated and quietly
rewriting what the candidate was asked.
"""
import hashlib
import secrets

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from postgrest.exceptions import APIError

from ..auth import CurrentUser, require_org
from ..config import settings
from ..db import service_client
from ..services import ai_interview, embeddings

router = APIRouter(prefix="/api", tags=["ai-interviews"])

# PostgREST renders bytea as a hex string with a leading \x and accepts the
# same form as a filter value. The digest itself is identical to what the
# database's ai_interview_token_hash() would compute for the same raw token.
def _token_hash(raw: str) -> str:
    return "\\x" + hashlib.sha256(raw.encode()).hexdigest()


def _session_by_token(token: str) -> dict:
    rows = (
        service_client().table("ai_interview_sessions").select("*")
        .eq("token_hash", _token_hash(token)).execute().data
    )
    if not rows:
        # Deliberately identical to the message for a revoked link: a probing
        # caller should not be able to tell a wrong token from a dead one.
        raise HTTPException(status_code=404, detail="This interview link is not valid.")
    return rows[0]


def _state(session_id: str) -> dict:
    """Resume state, computed by the database. `is_expired` and `is_open` are
    evaluated against the database's now(), not this process's clock."""
    rows = (
        service_client().table("ai_interview_session_state").select("*")
        .eq("session_id", session_id).execute().data
    )
    if not rows:
        raise HTTPException(status_code=404, detail="This interview link is not valid.")
    return rows[0]


def _role_context(session: dict) -> tuple[str, str]:
    db = service_client()
    if not session.get("role_id"):
        return "this role", ""
    rows = db.table("roles").select("title, description").eq("id", session["role_id"]).execute().data
    if not rows:
        return "this role", ""
    return rows[0]["title"], rows[0].get("description") or ""


def _turns(session_id: str) -> list[dict]:
    return (
        service_client().table("ai_interview_turns").select("*")
        .eq("session_id", session_id).order("ordinal").execute().data
    )


def _ensure_question(session: dict, state: dict) -> str:
    """Return the question the candidate should be looking at, generating and
    persisting it first if it does not exist yet."""
    if state.get("next_question_text"):
        return state["next_question_text"]           # resume: re-serve, never regenerate

    ordinal = state["next_ordinal"]
    role_title, jd = _role_context(session)
    turns = _turns(session["id"])

    if ordinal == 1:
        question, model = ai_interview.first_question(role_title, jd)
        source_ordinal = None
    else:
        prev = next((t for t in turns if t["ordinal"] == ordinal - 1), None)
        if not prev or not prev.get("answer_text"):
            # The turn gate would refuse this anyway; failing here gives a
            # comprehensible message instead of a raised PL/pgSQL exception.
            raise HTTPException(status_code=409, detail="The previous question is still unanswered.")
        question, model = ai_interview.next_question(
            role_title=role_title,
            jd=jd,
            ordinal=ordinal,
            target=session["question_target"],
            prev_question=prev["question_text"],
            prev_answer=prev["answer_text"],
            asked=[t["question_text"] for t in turns],
        )
        source_ordinal = ordinal - 1

    try:
        service_client().table("ai_interview_turns").insert({
            "organization_id": session["organization_id"],   # overwritten by the gate trigger
            "session_id": session["id"],
            "ordinal": ordinal,
            "question_text": question,
            "source_turn_ordinal": source_ordinal,
            "model": model,
        }).execute()
        return question
    except APIError as e:
        # Two tabs opened the same live link at the same moment. They collide on
        # uq_ai_turns_session_ordinal; the loser discards its question and serves
        # the winner's, so both tabs show the same thing.
        if e.code != "23505":
            raise
        rows = (
            service_client().table("ai_interview_turns").select("question_text")
            .eq("session_id", session["id"]).eq("ordinal", ordinal).execute().data
        )
        if not rows:
            raise
        return rows[0]["question_text"]


def _candidate_view(session: dict) -> dict:
    """Everything the candidate's page needs, and nothing about how they are
    being scored."""
    state = _state(session["id"])
    db = service_client()
    org = db.table("organizations").select("name").eq("id", session["organization_id"]).single().execute().data
    role_title, _ = _role_context(session)
    cand = db.table("candidates").select("full_name").eq("id", session["candidate_id"]).execute().data

    if state["is_expired"]:
        raise HTTPException(status_code=410, detail="This interview link has expired.")
    if state["status"] in ("completed", "scored", "scoring_rejected"):
        return {
            "state": "completed",
            "org_name": org["name"],
            "role_title": role_title,
            "candidate_name": cand[0]["full_name"] if cand else None,
            "answered": state["answered_count"],
            "question_target": state["question_target"],
        }

    question = _ensure_question(session, state)
    answered = state["answered_count"]
    return {
        "state": "in_progress",
        "org_name": org["name"],
        "role_title": role_title,
        "candidate_name": cand[0]["full_name"] if cand else None,
        "ordinal": state["next_ordinal"],
        "question_target": state["question_target"],
        "answered": answered,
        "question": question,
        # Prior turns come back too, so a resumed tab can show what was already
        # said rather than dropping the candidate into a bare question.
        "history": [
            {"ordinal": t["ordinal"], "question": t["question_text"], "answer": t["answer_text"]}
            for t in _turns(session["id"]) if t.get("answer_text")
        ],
        "expires_at": state["expires_at"],
    }


# ---------------------------------------------------------------------------
# Public, unauthenticated — the candidate's interview link
# ---------------------------------------------------------------------------

@router.get("/public/ai-interview/{token}")
def public_get_interview(token: str):
    return _candidate_view(_session_by_token(token))


class AnswerBody(BaseModel):
    ordinal: int = Field(ge=1, le=20)
    answer: str = Field(min_length=1)


@router.post("/public/ai-interview/{token}")
def public_submit_answer(token: str, body: AnswerBody):
    session = _session_by_token(token)
    state = _state(session["id"])

    if state["is_expired"]:
        raise HTTPException(status_code=410, detail="This interview link has expired.")
    if not state["is_open"]:
        raise HTTPException(status_code=410, detail="This interview is already complete.")

    rows = (
        service_client().table("ai_interview_turns").select("*")
        .eq("session_id", session["id"]).eq("ordinal", body.ordinal).execute().data
    )
    if not rows:
        raise HTTPException(status_code=409, detail="That question has not been asked yet.")
    if rows[0].get("answer_text"):
        # A double-submitted form, or a retry after a dropped response. The
        # transcript is append-only so this cannot overwrite; returning the
        # current view makes the retry a no-op instead of an error.
        return _candidate_view(session)
    if not body.answer.strip():
        raise HTTPException(status_code=400, detail="An answer cannot be blank.")

    service_client().table("ai_interview_turns").update(
        {"answer_text": body.answer}
    ).eq("id", rows[0]["id"]).execute()

    return _candidate_view(session)


# ---------------------------------------------------------------------------
# Recruiter side
# ---------------------------------------------------------------------------

class IssueBody(BaseModel):
    role_id: str | None = None
    question_target: int = Field(default=5, ge=1, le=20)


@router.post("/candidates/{candidate_id}/ai-interview", status_code=201)
def issue_interview_link(candidate_id: str, body: IssueBody, user: CurrentUser = Depends(require_org)):
    """Mint a single-use interview link.

    The session row is created HERE, at issue time, with the token hash UNIQUE
    on it. That is what makes "one token, one session" structural rather than a
    check that could be raced: there is no second row to create."""
    db = service_client()
    cand = (
        db.table("candidates").select("id, role_id, full_name")
        .eq("id", candidate_id).eq("organization_id", user.organization_id)
        .execute().data
    )
    if not cand:
        raise HTTPException(status_code=404, detail="Candidate not found")

    raw = secrets.token_urlsafe(32)
    session = db.table("ai_interview_sessions").insert({
        "organization_id": user.organization_id,
        "candidate_id": candidate_id,
        "role_id": body.role_id or cand[0].get("role_id"),
        "token_hash": _token_hash(raw),
        "question_target": body.question_target,
        "issued_by": user.user_id,
    }).execute().data[0]

    # The only time the raw token exists outside the candidate's URL bar. It is
    # not stored, so it cannot be recovered — reissue instead.
    return {
        "session": session,
        "link": f"{settings.frontend_url}/ai-interview/{raw}",
        "candidate_name": cand[0]["full_name"],
    }


@router.get("/ai-interviews")
def list_ai_interviews(user: CurrentUser = Depends(require_org)):
    return (
        service_client().table("ai_interview_sessions")
        .select("*, candidates(full_name, email), roles(title)")
        .eq("organization_id", user.organization_id)
        .order("created_at", desc=True).limit(200).execute().data
    )


@router.get("/ai-interviews/{session_id}")
def get_ai_interview(session_id: str, user: CurrentUser = Depends(require_org)):
    db = service_client()
    rows = (
        db.table("ai_interview_sessions").select("*, candidates(full_name, email), roles(title)")
        .eq("id", session_id).eq("organization_id", user.organization_id).execute().data
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Interview not found")

    scoped = lambda t: db.table(t).select("*").eq("session_id", session_id)
    return {
        "session": rows[0],
        "state": _state(session_id),
        "turns": _turns(session_id),
        # score_card only ever contains sessions that survived the evidence
        # check, so a rejected run shows an empty card plus a populated audit —
        # which is the honest presentation of "we scored it and did not
        # believe the result".
        "score_card": scoped("ai_interview_score_card").order("criterion_key").execute().data,
        "totals": scoped("ai_interview_score_totals").execute().data,
        "evidence_audit": scoped("ai_interview_evidence_audit").order("criterion_key").execute().data,
    }


@router.post("/ai-interviews/{session_id}/score")
def score_ai_interview(session_id: str, user: CurrentUser = Depends(require_org)):
    db = service_client()
    rows = (
        db.table("ai_interview_sessions").select("*")
        .eq("id", session_id).eq("organization_id", user.organization_id).execute().data
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Interview not found")
    session = rows[0]

    if session["status"] == "scored":
        raise HTTPException(status_code=409, detail="This interview is already scored.")
    if session["status"] not in ("completed", "scoring_rejected"):
        raise HTTPException(
            status_code=409,
            detail=f"Interview is {session['status']} — scoring runs on a completed interview.",
        )

    rubric = db.rpc("ai_interview_rubric_for", {
        "p_org": session["organization_id"], "p_role": session["role_id"]
    }).execute().data
    if not rubric:
        raise HTTPException(status_code=409, detail="No rubric resolves for this role.")

    role_title, jd = _role_context(session)
    turns = _turns(session_id)
    scored, model = ai_interview.score_transcript(role_title, jd, rubric, turns)
    by_key = {c.get("criterion_key"): c for c in scored if isinstance(c, dict)}

    payload = []
    for c in rubric:
        got = by_key.get(c["criterion_key"], {})
        # Clamped to the rubric's own range. A model that returns 7 out of 5
        # should not fail the whole card on a check constraint — but a criterion
        # the model omitted entirely gets an empty quote, which the evidence
        # trigger marks 'empty' and which correctly rejects the card rather
        # than passing a silent zero off as a judgement.
        raw_score = got.get("score", 0)
        try:
            score = max(0.0, min(float(raw_score), float(c["max_score"])))
        except (TypeError, ValueError):
            score = 0.0
        payload.append({
            "session_id": session_id,
            "organization_id": session["organization_id"],   # overwritten by trigger
            "criterion_key": c["criterion_key"],
            "label": c["label"],
            "score": score,
            "max_score": c["max_score"],
            "weight": c["weight"],
            "rationale": got.get("rationale"),
            "evidence_quote": got.get("evidence_quote") or "",
            "model": model,
        })

    db.table("ai_interview_scores").upsert(
        payload, on_conflict="session_id,criterion_key"
    ).execute()

    return get_ai_interview(session_id, user)


# ---------------------------------------------------------------------------
# Semantic search
# ---------------------------------------------------------------------------

class SearchBody(BaseModel):
    query: str = Field(min_length=2)
    limit: int = Field(default=20, ge=1, le=100)
    kinds: list[str] = ["profile", "transcript"]


@router.post("/search/semantic")
def semantic_search(body: SearchBody, user: CurrentUser = Depends(require_org)):
    bad = [k for k in body.kinds if k not in ("profile", "transcript")]
    if bad:
        raise HTTPException(status_code=400, detail=f"Unknown source kind: {bad[0]}")
    return embeddings.search(user.organization_id, body.query, body.limit, body.kinds)


@router.get("/embeddings/backlog")
def embedding_backlog(user: CurrentUser = Depends(require_org)):
    rows = (
        service_client().table("ai_embedding_backlog").select("*")
        .eq("organization_id", user.organization_id).execute().data
    )
    return {
        "pending": len(rows),
        "profiles": sum(1 for r in rows if r["source_kind"] == "profile"),
        "transcripts": sum(1 for r in rows if r["source_kind"] == "transcript"),
    }


@router.post("/embeddings/refresh")
def refresh_embeddings(user: CurrentUser = Depends(require_org)):
    return embeddings.refresh(user.organization_id)
