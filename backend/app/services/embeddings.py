"""NVIDIA NIM embeddings + pgvector semantic candidate search (Level 2).

What gets embedded, and in what shape:

  profiles     talent_pool.profile_text, chunked on paragraph boundaries.
  transcripts  ONE CHUNK PER ANSWERED TURN. That is not an arbitrary window
               size — the rubric's evidence check already matches per turn, so
               chunking the same way means a search hit and a score-card quote
               point at the same unit of text, and the snippet the recruiter
               sees is a whole answer rather than a sentence sawn in half.

What decides whether something needs embedding is the `ai_embedding_backlog`
view, which compares md5 of the live source text against the `source_hash`
stored at embed time. There is no dirty flag to forget to set: changed text is
always in the backlog, unchanged text never is.

Tenancy is not this module's decision. `organization_id` on an embedding row is
overwritten by the `ai_emb_bind_source` trigger from the source row, so passing
the wrong org here cannot file a vector under the wrong tenant.
"""
import time

from fastapi import HTTPException

from ..config import settings
from ..db import service_client
from .scoring import _RETRYABLE_CODES, _RETRY_DELAYS, _client

# nv-embedqa-e5-v5 accepts a batch per request; keep batches modest so one
# failure re-does little work and rate limits stay comfortable.
_BATCH = 16
_MAX_CHARS = 8000          # per chunk sent to the embedder
_PROFILE_CHUNK = 1500      # target profile chunk size, in characters


def _embed(texts: list[str], input_type: str) -> list[list[float]]:
    """Embed a list of texts. Returns vectors in the same order.

    `input_type` is NIM's asymmetric-retrieval switch ("query" or "passage").
    The API rejects any other value, so a typo fails loudly rather than
    silently embedding a query as a document.

    The returned width is fixed by the model (1024 for nv-embedqa-e5-v5) and is
    asserted below: a mismatch means the model was changed without migrating
    ai_embeddings.embedding, and failing here beats a Postgres error thrown
    halfway through a batch insert."""
    import openai

    if not texts:
        return []
    out: list[list[float]] = []
    for start in range(0, len(texts), _BATCH):
        batch = [t[:_MAX_CHARS] for t in texts[start : start + _BATCH]]
        last_error: Exception | None = None
        for delay in _RETRY_DELAYS:
            if delay:
                time.sleep(delay)
            try:
                resp = _client().embeddings.create(
                    model=settings.nvidia_embedding_model,
                    input=batch,
                    encoding_format="float",
                    extra_body={"input_type": input_type, "truncate": "END"},
                )
                # NIM returns items with an `index`; sort rather than trust order.
                vectors = [d.embedding for d in sorted(resp.data, key=lambda d: d.index)]
                for v in vectors:
                    if len(v) != settings.nvidia_embedding_dim:
                        raise HTTPException(
                            status_code=500,
                            detail=(
                                f"{settings.nvidia_embedding_model} returned {len(v)} dims, "
                                f"but ai_embeddings.embedding is vector("
                                f"{settings.nvidia_embedding_dim})."
                            ),
                        )
                out.extend(vectors)
                last_error = None
                break
            except (openai.RateLimitError, openai.APITimeoutError, openai.APIConnectionError) as e:
                last_error = e
                continue
            except openai.APIStatusError as e:
                if e.status_code in _RETRYABLE_CODES:
                    last_error = e
                    continue
                raise HTTPException(status_code=502, detail=f"NVIDIA embedding error: {e}")
        if last_error is not None:
            raise HTTPException(
                status_code=503,
                detail=f"NVIDIA embeddings unavailable after retries: {last_error}",
            )
    return out


def embed_query(text: str) -> list[float]:
    """A recruiter's search string. "query", not "passage" — the two embed into
    the same space but from different sides, and using the passage type for a
    query measurably hurts ranking."""
    return _embed([text], "query")[0]


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def chunk_profile(text: str) -> list[str]:
    """Split a profile on blank lines, packing paragraphs up to the target size.
    A single paragraph longer than the target is left whole rather than cut
    mid-sentence — _MAX_CHARS is the real ceiling and it is generous."""
    paras = [p.strip() for p in (text or "").split("\n\n") if p.strip()]
    chunks: list[str] = []
    current = ""
    for p in paras:
        if current and len(current) + len(p) + 2 > _PROFILE_CHUNK:
            chunks.append(current)
            current = p
        else:
            current = f"{current}\n\n{p}" if current else p
    if current:
        chunks.append(current)
    return chunks or ([text.strip()] if (text or "").strip() else [])


# ---------------------------------------------------------------------------
# The embedding pass
# ---------------------------------------------------------------------------

def _replace_chunks(key: str, source_id: str, chunks: list[str], org_id: str) -> int:
    """Delete-then-insert, because re-embedding shorter text must not leave the
    tail of the previous version behind: the unique index is on
    (source, chunk_ordinal), so an upsert would update chunks 0..n and orphan
    n+1.. as stale rows that still answer searches."""
    if not chunks:
        return 0
    db = service_client()
    vectors = _embed(chunks, "passage")
    db.table("ai_embeddings").delete().eq(key, source_id).execute()
    rows = [
        {
            key: source_id,
            # organization_id is required NOT NULL but is overwritten by the
            # ai_emb_bind_source trigger; source_hash likewise. Both are sent
            # only to satisfy the column definitions.
            "organization_id": org_id,
            "chunk_ordinal": i,
            "content": chunk,
            "source_hash": "",
            "embedding": vec,
            "model": settings.nvidia_embedding_model,
        }
        for i, (chunk, vec) in enumerate(zip(chunks, vectors))
    ]
    db.table("ai_embeddings").insert(rows).execute()
    return len(rows)


def refresh(organization_id: str, limit: int = 50) -> dict:
    """Embed everything in the backlog for one org. Idempotent: running it
    twice in a row does nothing the second time, because the first run's
    source_hash now matches."""
    db = service_client()
    backlog = (
        db.table("ai_embedding_backlog").select("*")
        .eq("organization_id", organization_id).limit(limit).execute().data
    )

    done = {"profiles": 0, "transcripts": 0, "chunks": 0, "skipped": 0}
    for item in backlog:
        if item["source_kind"] == "profile":
            rows = (
                db.table("talent_pool").select("profile_text")
                .eq("id", item["talent_pool_id"]).execute().data
            )
            chunks = chunk_profile(rows[0]["profile_text"]) if rows else []
            if not chunks:
                done["skipped"] += 1
                continue
            done["chunks"] += _replace_chunks(
                "talent_pool_id", item["talent_pool_id"], chunks, organization_id
            )
            done["profiles"] += 1
        else:
            turns = (
                db.table("ai_interview_turns")
                .select("ordinal, answer_text")
                .eq("session_id", item["session_id"])
                .not_.is_("answer_text", "null")
                .order("ordinal")
                .execute().data
            )
            chunks = [t["answer_text"].strip() for t in turns if (t.get("answer_text") or "").strip()]
            if not chunks:
                done["skipped"] += 1
                continue
            done["chunks"] += _replace_chunks(
                "session_id", item["session_id"], chunks, organization_id
            )
            done["transcripts"] += 1
    return done


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def search(organization_id: str, query: str, limit: int = 20,
           kinds: list[str] | None = None) -> list[dict]:
    """Semantic candidate search, scoped to one tenant.

    The organization_id is passed to the SQL function rather than filtered
    afterwards on this side. Post-filtering in Python would be a correctness
    bug wearing a performance costume: the ANN scan returns its top-N first, so
    stripping other tenants' rows here would silently return a short page while
    the matching rows for this tenant sat further down the graph, unvisited."""
    embedding = embed_query(query)
    res = service_client().rpc(
        "ai_search_candidates",
        {
            "p_query_embedding": embedding,
            "p_organization_id": organization_id,
            "p_limit": limit,
            "p_kinds": kinds or ["profile", "transcript"],
        },
    ).execute()
    # Cosine distance in [0, 2]; similarity is the friendlier number to show.
    for row in res.data or []:
        row["similarity"] = round(1.0 - float(row["distance"]), 4)
    return res.data or []
