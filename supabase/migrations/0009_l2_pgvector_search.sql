-- Phase 9 (Level 2): pgvector semantic candidate search.
--
-- pgvector is NOT currently enabled on this database. This migration turns it
-- on, so it is the one in this set with a real chance of failing on a plan that
-- does not offer the extension — run it first if you are applying them by hand.

-- Supabase installs extensions into `extensions`, but a database that ran
-- 0001's bare `create extension pgcrypto` may have one in `public`. Putting
-- both on the path means `vector` and `vector_cosine_ops` resolve either way.
set search_path = public, extensions;

-- `with schema extensions` is explicit rather than incidental. Without it the
-- extension lands in the first schema on the path — `public` — which is not
-- where this database keeps its extensions (pgcrypto and uuid-ossp are both in
-- `extensions`) and is what Supabase's own linter flags. The default role
-- search_path here is `"$user", public, extensions`, so `vector`,
-- `vector_cosine_ops` and the `<=>` operator all resolve for every role
-- without anyone having to set a search_path.
create extension if not exists vector with schema extensions;

-- ---------------------------------------------------------------------------
-- Where the vectors live
-- ---------------------------------------------------------------------------
-- build.md asks for the vectors "alongside the existing candidate rows". They
-- are — same database, real foreign keys, a join is a join — but in their own
-- table rather than as a column on talent_pool, because a transcript does not
-- fit in one vector. A five-turn interview is chunked, so one candidate has
-- many transcript vectors; a column could hold at most one. Once a table is
-- forced by transcripts, putting profiles in the same table means one index,
-- one query, and a single ranked list where a candidate's profile chunk and
-- their interview chunk compete on equal terms.
--
-- The source is two nullable foreign keys with a check that exactly one is set,
-- rather than a (source_table text, source_id uuid) pair. That keeps real
-- referential integrity and real ON DELETE CASCADE: deleting a candidate or a
-- session takes its vectors with it, which a polymorphic pair cannot promise.
create table if not exists public.ai_embeddings (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,

  talent_pool_id uuid references public.talent_pool(id) on delete cascade,
  session_id uuid references public.ai_interview_sessions(id) on delete cascade,
  source_kind text generated always as (
    case when talent_pool_id is not null then 'profile' else 'transcript' end
  ) stored,

  chunk_ordinal int not null default 0,
  content text not null,                       -- the matched snippet the UI shows
  source_hash text not null,                   -- md5 of the WHOLE source doc at embed time
  embedding vector(768) not null,              -- text-embedding-004 is 768-dimensional
  model text not null default 'text-embedding-004',
  created_at timestamptz not null default now(),

  constraint ai_emb_one_source check (num_nonnulls(talent_pool_id, session_id) = 1),
  constraint ai_emb_content_check check (btrim(content) <> ''),
  constraint ai_emb_chunk_check check (chunk_ordinal >= 0)
);

create unique index if not exists uq_ai_emb_profile
  on public.ai_embeddings(talent_pool_id, chunk_ordinal) where talent_pool_id is not null;
create unique index if not exists uq_ai_emb_transcript
  on public.ai_embeddings(session_id, chunk_ordinal) where session_id is not null;
create index if not exists idx_ai_emb_org on public.ai_embeddings(organization_id);

-- ---------------------------------------------------------------------------
-- Tenant binding
-- ---------------------------------------------------------------------------
-- organization_id is derived from the source row, never accepted from the
-- caller. Both RLS and the search filter key on this column, so a row filed
-- under the wrong org is a cross-tenant leak — and "the backend always passes
-- the right one" is an assumption, not a guarantee. source_hash is derived the
-- same way so it cannot claim a document is current when it is not.
create or replace function public.ai_embeddings_bind_source()
  returns trigger language plpgsql
as $fn$
declare
  src_org uuid;
begin
  if new.talent_pool_id is not null then
    select tp.organization_id, md5(coalesce(tp.profile_text, ''))
      into src_org, new.source_hash
      from public.talent_pool tp where tp.id = new.talent_pool_id;
  else
    select s.organization_id into src_org
      from public.ai_interview_sessions s where s.id = new.session_id;
    new.source_hash := md5(coalesce(public.ai_interview_transcript(new.session_id), ''));
  end if;

  if src_org is null then
    raise exception 'ai_embeddings: source row not found';
  end if;
  new.organization_id := src_org;
  return new;
end
$fn$;

drop trigger if exists ai_emb_bind_source on public.ai_embeddings;
create trigger ai_emb_bind_source before insert or update
  on public.ai_embeddings
  for each row execute function public.ai_embeddings_bind_source();

-- ---------------------------------------------------------------------------
-- The index
-- ---------------------------------------------------------------------------
-- HNSW over cosine distance.
--
-- Cosine, because Gemini's text-embedding-004 vectors are compared by cosine
-- similarity and are not unit-normalised on the way in; using L2 would rank by
-- a distance the model was not trained to mean anything by.
--
-- HNSW rather than IVFFlat, for three reasons that all point the same way here:
--
--   1. IVFFlat's lists must be tuned to the row count and the index has to be
--      built on populated data — building it now, on an empty table, produces
--      centroids from nothing and recall collapses. This migration runs before
--      a single candidate is embedded. HNSW has no training step.
--   2. This is a recruiting database: thousands to low millions of chunks, not
--      hundreds of millions. HNSW's higher build cost and memory footprint is
--      the side of the tradeoff worth paying at this size, and it gives better
--      recall at the same latency.
--   3. IVFFlat needs periodic REINDEX as the distribution shifts. Nothing in
--      this system would remember to do that.
--
-- m=16 / ef_construction=64 are pgvector's defaults and are the right starting
-- point; raise ef_construction before m if recall proves short.
--
-- THE ACTUAL RISK IS THE TENANT FILTER, not the index type. Every search is
-- `where organization_id = $1 order by embedding <=> $2 limit n`, and pgvector
-- POST-filters: it walks the graph, then discards rows belonging to other orgs.
-- With many orgs in one table, a small candidate list can be almost entirely
-- other tenants' rows and the query returns fewer than n results — or none —
-- while the data is sitting right there. That is a silent wrong answer, not an
-- error. Mitigated in ai_search_candidates() below by raising hnsw.ef_search
-- and enabling iterative scans; a per-org partial index would be exact but
-- needs one index per tenant, which does not scale.
create index if not exists idx_ai_emb_hnsw
  on public.ai_embeddings using hnsw (embedding vector_cosine_ops)
  with (m = 16, ef_construction = 64);

-- ---------------------------------------------------------------------------
-- Search
-- ---------------------------------------------------------------------------
-- Not marked STABLE: it sets transaction-local GUCs, and it should never be
-- folded or cached by the planner.
create or replace function public.ai_search_candidates(
  p_query_embedding vector(768),
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
  -- Two independent guards, because this function is called both ways. Under
  -- `authenticated` the RLS policy below already scopes the read, and this
  -- check just turns a silently-empty result into a clear 42501. Under the
  -- backend's service role RLS is bypassed entirely, and the explicit
  -- organization_id filter in the query is the only thing standing between
  -- tenants — which is why it is on the query, not left to the caller.
  if coalesce(auth.role(), '') <> 'service_role'
     and not public.is_org_member(p_organization_id) then
    raise exception 'ai_search_candidates: not a member of organization %', p_organization_id
      using errcode = '42501';
  end if;

  -- Widen the candidate list before post-filtering strips other tenants' rows.
  -- iterative_scan (pgvector 0.8+) makes the scan keep going until it has
  -- enough rows that survive the filter instead of returning short; on an older
  -- pgvector the setting is simply inert, and ef_search still helps.
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

-- ---------------------------------------------------------------------------
-- What still needs embedding
-- ---------------------------------------------------------------------------
-- Drives the backend's embedding pass. Comparing md5 of the current source text
-- against the hash stored at embed time means unchanged text is never
-- re-embedded and changed text always is — no updated_at bookkeeping, no
-- "dirty" flag to forget to set.
create or replace view public.ai_embedding_backlog
with (security_invoker = on) as
select
  'profile'::text as source_kind,
  tp.organization_id,
  tp.id           as talent_pool_id,
  null::uuid      as session_id
from public.talent_pool tp
where btrim(coalesce(tp.profile_text, '')) <> ''
  and not exists (
    select 1 from public.ai_embeddings e
     where e.talent_pool_id = tp.id
       and e.source_hash = md5(tp.profile_text)
  )
union all
select
  'transcript'::text,
  s.organization_id,
  null::uuid,
  s.id
from public.ai_interview_sessions s
where s.status in ('completed', 'scored', 'scoring_rejected')
  and not exists (
    select 1 from public.ai_embeddings e
     where e.session_id = s.id
       and e.source_hash = md5(coalesce(public.ai_interview_transcript(s.id), ''))
  );

-- ---------------------------------------------------------------------------
-- Row Level Security
-- ---------------------------------------------------------------------------
alter table public.ai_embeddings enable row level security;

-- Read-only for org members. Writes are the embedding pass, which runs as the
-- service role. build.md: "search must never cross tenants" — this policy is
-- the second of the two guards described on ai_search_candidates().
drop policy if exists ai_emb_select on public.ai_embeddings;
create policy ai_emb_select on public.ai_embeddings
  for select using (public.is_org_member(organization_id));
