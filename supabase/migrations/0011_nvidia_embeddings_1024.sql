-- Phase 11: migrate the embedding space from Gemini (768) to NVIDIA NIM (1024).
--
-- nvidia/nv-embedqa-e5-v5 emits 1024-dimensional vectors, so vector(768) can no
-- longer hold them. The width is the visible half of the change; the important
-- half is that this is a DIFFERENT VECTOR SPACE. Vectors from two models are
-- not comparable even when the widths happen to match, so old rows cannot be
-- kept, padded or converted — the distances would be arithmetically valid and
-- semantically meaningless, which is the worst kind of wrong. Every embedding
-- is therefore discarded and rebuilt from source text.
--
-- Nothing is lost by truncating: ai_embeddings is a derived cache. The source
-- of truth is talent_pool.profile_text and ai_interview_turns.answer_text, and
-- the ai_embedding_backlog view (unchanged here) compares md5 of that live text
-- against source_hash — so emptying this table puts every row straight back
-- into the backlog, and the existing "Embed backlog" action refills it.

-- The HNSW index and the search function both bind the column's dimension, so
-- both have to go before the type change and be rebuilt after it.
drop index if exists public.idx_ai_emb_hnsw;

-- A changed argument type is a new signature: CREATE OR REPLACE cannot do it,
-- and leaving the old one behind would give PostgREST two overloads to choose
-- between and an ambiguous-function error at call time.
drop function if exists public.ai_search_candidates(vector(768), uuid, int, text[]);

-- Derived data, rebuilt by the backlog pass. Not DELETE: this empties the whole
-- table by design and TRUNCATE skips the per-row work and the dead tuples.
truncate table public.ai_embeddings;

alter table public.ai_embeddings
  alter column embedding type vector(1024);

-- The default recorded the model that produced a row; point it at the new one
-- so rows written before the backend redeploys are not mislabelled.
alter table public.ai_embeddings
  alter column model set default 'nvidia/nv-embedqa-e5-v5';

-- Rebuilt identically, only wider. Same opclass: nv-embedqa vectors are
-- normalised, but cosine stays correct either way and matches the <=> operator
-- the search function orders by.
create index if not exists idx_ai_emb_hnsw
  on public.ai_embeddings using hnsw (embedding vector_cosine_ops)
  with (m = 16, ef_construction = 64);

-- Recreated verbatim from 0009 apart from the parameter width. The two tenancy
-- guards, the ef_search widening and the iterative scan all still apply and are
-- documented there.
create or replace function public.ai_search_candidates(
  p_query_embedding vector(1024),
  p_organization_id uuid,
  p_limit int default 20,
  p_kinds text[] default array['profile', 'transcript']
)
returns table (
  embedding_id uuid,
  source_kind text,
  candidate_name text,
  talent_pool_id uuid,
  session_id uuid,
  candidate_id uuid,
  chunk_ordinal int,
  snippet text,
  distance double precision
)
language plpgsql
as $fn$
begin
  if coalesce(auth.role(), '') <> 'service_role'
     and not public.is_org_member(p_organization_id) then
    raise exception 'ai_search_candidates: not a member of organization %', p_organization_id
      using errcode = '42501';
  end if;

  perform set_config('hnsw.ef_search', '200', true);
  perform set_config('hnsw.iterative_scan', 'relaxed_order', true);

  return query
  select
    e.id,
    e.source_kind,
    coalesce(tp.full_name, c.full_name),
    e.talent_pool_id,
    e.session_id,
    s.candidate_id,
    e.chunk_ordinal,
    e.content,
    (e.embedding <=> p_query_embedding)::double precision
  from public.ai_embeddings e
  left join public.talent_pool tp on tp.id = e.talent_pool_id
  left join public.ai_interview_sessions s on s.id = e.session_id
  left join public.candidates c on c.id = s.candidate_id
  where e.organization_id = p_organization_id
    and e.source_kind = any (p_kinds)
  order by e.embedding <=> p_query_embedding
  limit greatest(coalesce(p_limit, 20), 1);
end
$fn$;
