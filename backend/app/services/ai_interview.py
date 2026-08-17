"""Asynchronous AI interviews (Level 2).

Two Gemini jobs live here and nothing else:

  1. Generating the next question. Q1 comes from the role description. Q2
     onwards are conditioned on the previous answer — the prompt is handed that
     answer verbatim, so the question could not have been written in advance.
  2. Scoring a finished transcript against the rubric, with a verbatim evidence
     quote per criterion.

The evidence quote is NOT trusted here. A model asked nicely to quote verbatim
will still paraphrase, so whether a quote is real is decided by the
`ai_scores_check_evidence` trigger string-matching it against the stored turns.
This module's job is to ask for a good quote; the database's job is to refuse a
bad one. Do not add a "looks close enough" check on this side — it would
disagree with the trigger, and the trigger is the one that counts.

Persistence is deliberately absent from this file: it belongs to the router,
which owns the ordering guarantee (question written before it is shown).
"""
import re

from ..config import settings
from .scoring import _generate_json

# ---------------------------------------------------------------------------
# Evidence pre-check
# ---------------------------------------------------------------------------
# These mirror ai_squash_ws / ai_min_evidence_words / ai_min_evidence_chars from
# migration 0008. The database trigger remains the authority — this is a local
# copy so a bad quote can be caught and REPAIRED before it is written, rather
# than only discovered afterwards when it has already rejected the whole card.
# If the SQL thresholds change, change these to match.
_MIN_EVIDENCE_WORDS = 5
_MIN_EVIDENCE_CHARS = 25

# Two repair rounds. The first catches ordinary paraphrase; a criterion still
# unquotable after two is usually one the transcript genuinely does not support,
# and further rounds just cost minutes on the quality model.
_EVIDENCE_REPAIR_ATTEMPTS = 2


def _squash_ws(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def check_evidence(quote: str | None, answers: list[str]) -> str:
    """Return the verdict the trigger would reach: 'verbatim', 'empty',
    'not_verbatim' or 'too_short'."""
    if not (quote or "").strip():
        return "empty"
    q = _squash_ws(quote)
    if not any(q in _squash_ws(a) for a in answers if a):
        return "not_verbatim"
    if len(q.split(" ")) < _MIN_EVIDENCE_WORDS or len(q) < _MIN_EVIDENCE_CHARS:
        return "too_short"
    return "verbatim"

# ---------------------------------------------------------------------------
# Question generation
# ---------------------------------------------------------------------------

QUESTION_SCHEMA = {
    "type": "object",
    "properties": {"question": {"type": "string"}},
    "required": ["question"],
}

_INTERVIEWER_RULES = """You are conducting a written screening interview. You are talking
to the candidate directly.

Rules:
- Ask exactly ONE question. No preamble, no numbering, no "Great answer!".
- Plain text, no markdown. Under 60 words.
- It must be answerable in a few paragraphs of writing, with no code, no
  whiteboard and no access to a machine.
- Ask about what they have actually done. Never ask a trivia question, a
  brainteaser, or anything answerable from a job title alone.
- Never ask for personal characteristics: age, nationality, health, religion,
  family, or anything else it would be unlawful to hire on.
"""

FIRST_QUESTION_PROMPT = """{rules}
This is the OPENING question of the interview. Ground it in the role below —
pick the single most load-bearing requirement and ask the candidate to describe
concrete work of that kind that they personally did.

ROLE: {role_title}

JOB DESCRIPTION:
{jd}
"""

# The prior answer is handed over verbatim and the model is told to build on it.
# This is what makes the question un-pre-writable, and `source_turn_ordinal` on
# the turn row records which answer it was built on so the claim is checkable
# from the data rather than from a screenshot.
NEXT_QUESTION_PROMPT = """{rules}
This is question {ordinal} of {target}. Below is the exchange that just
happened. Your question MUST follow from what the candidate actually said —
pick the most interesting specific claim, decision, or gap in their answer and
probe it one level deeper. Refer to their own words so it is obvious you read
them.

Do not change the subject. Do not re-ask anything in the "ALREADY ASKED" list.

ROLE: {role_title}

JOB DESCRIPTION:
{jd}

ALREADY ASKED:
{asked}

THE QUESTION THEY WERE JUST ASKED:
{prev_question}

THEIR ANSWER, VERBATIM:
{prev_answer}
"""


def first_question(role_title: str, jd: str) -> tuple[str, str]:
    """Returns (question_text, model)."""
    data, model = _generate_json(
        FIRST_QUESTION_PROMPT.format(
            rules=_INTERVIEWER_RULES,
            role_title=role_title or "this role",
            jd=(jd or "No job description was provided.")[:20000],
        ),
        QUESTION_SCHEMA,
    )
    return data["question"].strip(), model


def next_question(
    role_title: str,
    jd: str,
    ordinal: int,
    target: int,
    prev_question: str,
    prev_answer: str,
    asked: list[str],
) -> tuple[str, str]:
    """Returns (question_text, model). `prev_answer` is passed through
    untouched — truncating it here would be truncating the thing the whole
    design turns on."""
    data, model = _generate_json(
        NEXT_QUESTION_PROMPT.format(
            rules=_INTERVIEWER_RULES,
            ordinal=ordinal,
            target=target,
            role_title=role_title or "this role",
            jd=(jd or "No job description was provided.")[:20000],
            asked="\n".join(f"- {q}" for q in asked) or "(nothing yet)",
            prev_question=prev_question,
            prev_answer=prev_answer[:20000],
        ),
        QUESTION_SCHEMA,
    )
    return data["question"].strip(), model


# ---------------------------------------------------------------------------
# Rubric scoring
# ---------------------------------------------------------------------------

SCORING_SCHEMA = {
    "type": "object",
    "properties": {
        "criteria": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "criterion_key": {"type": "string"},
                    "score": {"type": "number"},
                    "rationale": {"type": "string"},
                    "evidence_quote": {"type": "string"},
                },
                "required": ["criterion_key", "score", "rationale", "evidence_quote"],
            },
        }
    },
    "required": ["criteria"],
}

# Re-ask for ONLY the criteria whose quote failed, with the offending quote shown
# back. Naming the specific failure works far better than repeating the general
# rule, which the model already had and did not follow.
REPAIR_PROMPT = """Some evidence quotes you returned are not present in the candidate's
answers, so they were rejected. Fix ONLY the criteria listed below.

For each one, find a real, contiguous run of the candidate's own words in the
ANSWERS and copy it out character for character. Do not summarise, do not merge
sentences from different places, do not add arrows, bullets or connectors that
are not in their text. If a criterion genuinely has no support anywhere in the
answers, return an empty string for evidence_quote and score it low — a blank is
accepted, a fabricated quote is not.

Quote at least 5 words and at least 25 characters.

CRITERIA TO FIX (with the quote that was rejected, and why):
{failures}

RUBRIC:
{rubric}

CANDIDATE'S ANSWERS — the only text you may quote from:
{answers}
"""

SCORING_PROMPT = """You are scoring a completed written interview against a rubric.

Score EVERY criterion listed. Return exactly one entry per criterion, using the
criterion_key exactly as given.

THE EVIDENCE RULE — this is the part that gets checked mechanically:
- `evidence_quote` must be copied CHARACTER FOR CHARACTER from the candidate's
  ANSWERS below. It is string-matched against the stored transcript.
- Do not tidy it. Do not fix their spelling, expand a contraction, translate,
  summarise, or join two sentences that were not adjacent. Copy a contiguous run
  of their text and nothing else.
- Never quote the interviewer's questions. A criterion that proves itself by
  quoting the question has proved nothing.
- Quote at least 5 words, and at least 25 characters.
- If the transcript genuinely contains no support for a criterion, return an
  empty string for evidence_quote and score it low. An invented quote rejects
  the entire score card, so a blank is far better than a plausible fabrication.

Score each criterion from 0 to its max, judged only on what is in the
transcript. Keep each rationale to 1-3 sentences.

ROLE: {role_title}

JOB DESCRIPTION:
{jd}

RUBRIC:
{rubric}

TRANSCRIPT:
{transcript}
"""


def score_transcript(role_title: str, jd: str, rubric: list[dict], turns: list[dict]) -> tuple[list[dict], str]:
    """Score a completed interview. Returns (criteria, model).

    `turns` are the stored rows, in order; questions are shown for context but
    the prompt is explicit that only answers may be quoted."""
    rubric_text = "\n".join(
        f"- {c['criterion_key']} — {c['label']} (0 to {c['max_score']}): {c['description']}"
        for c in rubric
    )
    transcript = "\n\n".join(
        f"Q{t['ordinal']} (interviewer, NOT quotable): {t['question_text']}\n"
        f"A{t['ordinal']} (candidate, quotable): {t.get('answer_text') or '(unanswered)'}"
        for t in turns
    )
    data, model = _generate_json(
        SCORING_PROMPT.format(
            role_title=role_title or "this role",
            jd=(jd or "No job description was provided.")[:20000],
            rubric=rubric_text,
            transcript=transcript[:60000],
        ),
        SCORING_SCHEMA,
        # Quality model: this decides how a candidate is judged, runs once per
        # completed interview, and nobody is sitting watching it — the opposite
        # trade-off from question generation, which the candidate waits on.
        model=settings.nvidia_quality_model,
    )
    criteria = data.get("criteria", [])

    # ---- repair pass ----------------------------------------------------
    # One bad quote rejects the ENTIRE card (by design — see 0008), so with five
    # criteria a 90%-per-criterion model still fails ~4 cards in 10. Verifying
    # here and re-asking only for the failures converts that into a card that
    # almost always survives, without weakening the check itself: anything still
    # unverifiable after the retries is blanked, and a blank scores low rather
    # than passing a fabrication off as evidence.
    answers = [t.get("answer_text") or "" for t in turns]
    if any(answers):
        rubric_by_key = {c["criterion_key"]: c for c in rubric}
        for _ in range(_EVIDENCE_REPAIR_ATTEMPTS):
            failures = [
                (c, check_evidence(c.get("evidence_quote"), answers))
                for c in criteria
                if isinstance(c, dict) and c.get("criterion_key") in rubric_by_key
            ]
            # 'empty' is a legitimate answer — the model saying it found nothing.
            # Only quotes that claim to be citations but are not get repaired.
            broken = [(c, v) for c, v in failures if v in ("not_verbatim", "too_short")]
            if not broken:
                break

            listing = "\n".join(
                f"- {c['criterion_key']}: rejected as {v}\n"
                f"  you returned: {(c.get('evidence_quote') or '')[:300]!r}"
                for c, v in broken
            )
            rubric_text = "\n".join(
                f"- {rubric_by_key[c['criterion_key']]['criterion_key']} — "
                f"{rubric_by_key[c['criterion_key']]['label']}: "
                f"{rubric_by_key[c['criterion_key']]['description']}"
                for c, _ in broken
            )
            answers_text = "\n\n".join(
                f"A{t['ordinal']}: {t.get('answer_text') or '(unanswered)'}" for t in turns
            )
            fixed, _ = _generate_json(
                REPAIR_PROMPT.format(
                    failures=listing, rubric=rubric_text, answers=answers_text[:60000]
                ),
                SCORING_SCHEMA,
                model=settings.nvidia_quality_model,
            )
            repaired = {
                f.get("criterion_key"): f
                for f in fixed.get("criteria", []) if isinstance(f, dict)
            }
            for c, _v in broken:
                r = repaired.get(c["criterion_key"])
                if not r:
                    continue
                # Keep the original score/rationale unless the repair supplies
                # its own; only the quote is actually under repair here.
                c["evidence_quote"] = r.get("evidence_quote") or ""
                if r.get("rationale"):
                    c["rationale"] = r["rationale"]
                if isinstance(r.get("score"), (int, float)):
                    c["score"] = r["score"]

        # Anything still fabricated after the retries is blanked rather than
        # written: 'empty' is honest, 'not_verbatim' is a false citation.
        for c in criteria:
            if not isinstance(c, dict):
                continue
            if check_evidence(c.get("evidence_quote"), answers) in ("not_verbatim", "too_short"):
                c["evidence_quote"] = ""

    return criteria, model
