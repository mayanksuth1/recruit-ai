-- Phase 8 (Level 2): rubric scoring with evidence that must be in the transcript.
--
-- build.md: "Each criterion gets a score and a verbatim evidence quote lifted
-- from the transcript. A criterion whose quote does not appear in the stored
-- transcript is invalid — the scoring is rejected and flagged, not stored with
-- the bad quote."
--
-- Read literally, that is a per-criterion test with a per-SESSION consequence:
-- one unsupported quote rejects the whole score card. That is the right shape.
-- A card showing four honest criteria and one invented one is more dangerous
-- than no card, because the four make the fifth look checked.
--
-- The check lives in the database, not in the prompt. A model asked nicely to
-- quote verbatim will still paraphrase; the only reliable test is string
-- matching against the stored rows, and the only place that cannot be skipped
-- is a trigger.

-- ---------------------------------------------------------------------------
-- Comparators
-- ---------------------------------------------------------------------------
-- Whitespace-squashing comparator. Answers arrive from a textarea carrying
-- newlines and runs of spaces, and models re-flow what they quote, so a
-- byte-exact match would reject quotes that are genuinely verbatim. Case is NOT
-- folded — "verbatim" means verbatim.
create or replace function public.ai_squash_ws(t text)
  returns text language sql immutable strict
as $fn$
  select regexp_replace(btrim(t), '\s+', ' ', 'g')
$fn$;

create or replace function public.ai_word_count(t text)
  returns integer language sql immutable strict
as $fn$
  select cardinality(regexp_split_to_array(public.ai_squash_ws(t), ' '))
$fn$;

-- What counts as a substantial quote. Measured primarily in WORDS: project 01
-- shipped a 40-character floor first and it rejected "Acme Ltd builds warehouse
-- robots." (33 chars) — a complete, specific, perfectly good sentence. It also
-- shipped with no floor at all, and a two-word fragment matched a real page and
-- was accepted as evidence. Word count tracks "is this a clause or a noun
-- phrase" far better than length does; the character floor only exists to catch
-- five very short tokens.
create or replace function public.ai_min_evidence_words()
  returns integer language sql immutable as $fn$ select 5 $fn$;

create or replace function public.ai_min_evidence_chars()
  returns integer language sql immutable as $fn$ select 25 $fn$;

-- ---------------------------------------------------------------------------
-- Rubric
-- ---------------------------------------------------------------------------
-- Three tiers, most specific wins: a rubric for one role, else the org's own
-- default, else the global template seeded at the bottom of this file. The
-- global tier is what makes a brand-new org scoreable on day one without a
-- bootstrap step; the org and role tiers are what make "change how we score"
-- a row edit rather than a deploy.
create table if not exists public.ai_interview_rubric_criteria (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid references public.organizations(id) on delete cascade,
  role_id uuid references public.roles(id) on delete cascade,

  criterion_key text not null,
  label text not null,
  description text not null default '',        -- shown to the model as the standard
  weight numeric not null default 1.0,
  max_score numeric not null default 5,
  display_order int not null default 0,
  active boolean not null default true,
  created_at timestamptz not null default now(),

  constraint ai_rubric_key_check check (criterion_key ~ '^[a-z][a-z0-9_]{2,39}$'),
  constraint ai_rubric_weight_check check (weight > 0),
  constraint ai_rubric_max_check check (max_score > 0),
  -- A role-scoped criterion must name the org that owns the role.
  constraint ai_rubric_scope_check check (role_id is null or organization_id is not null)
);

create unique index if not exists uq_ai_rubric_global
  on public.ai_interview_rubric_criteria(criterion_key)
  where organization_id is null;
create unique index if not exists uq_ai_rubric_org
  on public.ai_interview_rubric_criteria(organization_id, criterion_key)
  where organization_id is not null and role_id is null;
create unique index if not exists uq_ai_rubric_role
  on public.ai_interview_rubric_criteria(organization_id, role_id, criterion_key)
  where role_id is not null;

-- Tier resolution. 1 = this role, 2 = this org, 3 = global; the whole rubric
-- comes from the single most specific tier that has any active row, so a
-- role-level rubric REPLACES the org default rather than merging with it —
-- a half-inherited rubric would be impossible to reason about.
create or replace function public.ai_interview_rubric_for(p_org uuid, p_role uuid)
  returns setof public.ai_interview_rubric_criteria
  language sql stable
as $fn$
  with visible as (
    select c.*,
           case when c.role_id is not null then 1
                when c.organization_id is not null then 2
                else 3 end as tier
      from public.ai_interview_rubric_criteria c
     where c.active
       and (c.organization_id is null
            or (c.organization_id = p_org
                and (c.role_id is null or c.role_id = p_role)))
  )
  select v.id, v.organization_id, v.role_id, v.criterion_key, v.label,
         v.description, v.weight, v.max_score, v.display_order, v.active,
         v.created_at
    from visible v
   where v.tier = (select min(tier) from visible)
   order by v.display_order, v.criterion_key
$fn$;

-- ---------------------------------------------------------------------------
-- Scores
-- ---------------------------------------------------------------------------
-- weight and max_score are SNAPSHOTTED onto the row. Editing the rubric must
-- change what the next scoring run produces, not silently restate a score card
-- a recruiter already read and acted on.
create table if not exists public.ai_interview_scores (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null,               -- set from the session by the trigger
  session_id uuid not null references public.ai_interview_sessions(id) on delete cascade,
  criterion_key text not null,

  label text not null default '',
  score numeric not null,
  max_score numeric not null default 5,
  weight numeric not null default 1.0,
  rationale text,

  evidence_quote text,
  evidence_check text not null default 'unchecked',
  evidence_turn_ordinal int,                   -- which answer the quote came from
  evidence_offset int,                         -- 1-based char offset within that answer

  model text,
  scored_at timestamptz not null default now(),

  constraint ai_scores_check_check check (evidence_check in
    ('unchecked', 'verbatim', 'empty', 'no_transcript', 'not_verbatim', 'too_short')),
  constraint ai_scores_range_check check (score >= 0 and score <= max_score)
);

-- Natural key. Re-scoring a criterion is an ON CONFLICT DO UPDATE, never a
-- SELECT-then-INSERT.
create unique index if not exists uq_ai_scores_session_criterion
  on public.ai_interview_scores(session_id, criterion_key);
create index if not exists idx_ai_scores_org on public.ai_interview_scores(organization_id);

-- ---------------------------------------------------------------------------
-- The evidence check
-- ---------------------------------------------------------------------------
-- Matching is done PER TURN, not against the concatenated transcript. A quote
-- that only matches once two answers are glued together spans a boundary the
-- candidate never spoke across — it is an artifact of concatenation, not
-- something they said. Per-turn matching also yields the location the score
-- card links to, for free.
create or replace function public.ai_interview_check_evidence()
  returns trigger language plpgsql
as $fn$
declare
  s public.ai_interview_sessions%rowtype;
  quote_ws text;
  hit record;
  answered int;
begin
  select * into s from public.ai_interview_sessions where id = new.session_id;
  if not found then
    raise exception 'ai_interview_scores: session % does not exist', new.session_id;
  end if;

  new.organization_id := s.organization_id;

  -- Scoring is only meaningful over a finished interview, and a finished score
  -- card is final. 'completed' is only reachable once every turn is answered,
  -- so this is also what enforces "scoring once all five turns exist".
  if s.status not in ('completed', 'scoring_rejected') then
    raise exception 'ai_interview_scores: session % is % — scoring runs on a completed, unscored interview',
      s.id, s.status;
  end if;

  select count(*) into answered
    from public.ai_interview_turns
   where session_id = new.session_id and answer_text is not null;

  quote_ws := public.ai_squash_ws(new.evidence_quote);

  if new.evidence_quote is null or btrim(new.evidence_quote) = '' then
    new.evidence_check := 'empty';
  elsif answered = 0 then
    new.evidence_check := 'no_transcript';
  else
    select t.ordinal,
           position(quote_ws in public.ai_squash_ws(t.answer_text)) as off
      into hit
      from public.ai_interview_turns t
     where t.session_id = new.session_id
       and t.answer_text is not null
       and position(quote_ws in public.ai_squash_ws(t.answer_text)) > 0
     order by t.ordinal
     limit 1;

    if not found then
      new.evidence_check := 'not_verbatim';
    elsif public.ai_word_count(new.evidence_quote) < public.ai_min_evidence_words()
       or length(quote_ws) < public.ai_min_evidence_chars() then
      -- It IS in the transcript, but it is a fragment, not a citation.
      new.evidence_check := 'too_short';
    else
      new.evidence_check := 'verbatim';
      new.evidence_turn_ordinal := hit.ordinal;
      new.evidence_offset := hit.off;
    end if;
  end if;

  if new.evidence_check <> 'verbatim' then
    new.evidence_turn_ordinal := null;
    new.evidence_offset := null;
  end if;

  return new;
end
$fn$;

drop trigger if exists ai_scores_check_evidence on public.ai_interview_scores;
create trigger ai_scores_check_evidence before insert or update
  on public.ai_interview_scores
  for each row execute function public.ai_interview_check_evidence();

-- ---------------------------------------------------------------------------
-- Session verdict
-- ---------------------------------------------------------------------------
-- Recomputed from scratch on every write. Runs once per criterion rather than
-- once per batch, which for a five-row rubric is cheaper than the transition
-- tables and upsert-firing rules needed to do it statement-at-a-time.
create or replace function public.ai_interview_settle_scoring()
  returns trigger language plpgsql
as $fn$
declare
  sid uuid := coalesce(new.session_id, old.session_id);
  s public.ai_interview_sessions%rowtype;
  expected int;
  got int;
  bad int;
begin
  select * into s from public.ai_interview_sessions where id = sid;
  if not found then
    return null;                                -- session cascade-deleted
  end if;

  select count(*) into expected
    from public.ai_interview_rubric_for(s.organization_id, s.role_id);

  select count(*), count(*) filter (where evidence_check <> 'verbatim')
    into got, bad
    from public.ai_interview_scores where session_id = sid;

  if bad > 0 then
    if s.status = 'completed' then
      update public.ai_interview_sessions set status = 'scoring_rejected' where id = sid;
    end if;
  elsif got > 0 and got >= expected and s.status in ('completed', 'scoring_rejected') then
    update public.ai_interview_sessions set status = 'scored' where id = sid;
  end if;

  return null;
end
$fn$;

drop trigger if exists ai_scores_settle on public.ai_interview_scores;
create trigger ai_scores_settle after insert or update or delete
  on public.ai_interview_scores
  for each row execute function public.ai_interview_settle_scoring();

-- ---------------------------------------------------------------------------
-- Reading the result
-- ---------------------------------------------------------------------------
-- The score card. Only sessions that survived the evidence check appear here,
-- so a rejected scoring run is absent from the card entirely rather than
-- present with a caveat.
create or replace view public.ai_interview_score_card
with (security_invoker = on) as
select
  sc.session_id,
  sc.organization_id,
  s.candidate_id,
  s.role_id,
  sc.criterion_key,
  sc.label,
  sc.score,
  sc.max_score,
  sc.weight,
  sc.rationale,
  sc.evidence_quote,
  sc.evidence_turn_ordinal,
  sc.evidence_offset,
  sc.model,
  sc.scored_at
from public.ai_interview_scores sc
join public.ai_interview_sessions s on s.id = sc.session_id
where s.status = 'scored'
order by sc.session_id, sc.criterion_key;

create or replace view public.ai_interview_score_totals
with (security_invoker = on) as
select
  sc.session_id,
  sc.organization_id,
  s.candidate_id,
  s.role_id,
  count(*)                                                        as criteria,
  round(sum(sc.score * sc.weight), 3)                             as weighted_score,
  round(sum(sc.max_score * sc.weight), 3)                         as weighted_max,
  round(100 * sum(sc.score * sc.weight)
            / nullif(sum(sc.max_score * sc.weight), 0), 1)        as percent
from public.ai_interview_scores sc
join public.ai_interview_sessions s on s.id = sc.session_id
where s.status = 'scored'
group by sc.session_id, sc.organization_id, s.candidate_id, s.role_id;

-- Every criterion including the rejected ones, with the verdict spelled out.
-- This is where a 'not_verbatim' quote goes to be looked at; it is deliberately
-- not the score card.
create or replace view public.ai_interview_evidence_audit
with (security_invoker = on) as
select
  sc.session_id,
  sc.organization_id,
  s.status                                        as session_status,
  sc.criterion_key,
  sc.evidence_check,
  public.ai_word_count(sc.evidence_quote)         as evidence_words,
  length(public.ai_squash_ws(sc.evidence_quote))  as evidence_chars,
  sc.evidence_turn_ordinal,
  sc.evidence_offset,
  sc.evidence_quote
from public.ai_interview_scores sc
join public.ai_interview_sessions s on s.id = sc.session_id;

-- ---------------------------------------------------------------------------
-- Row Level Security
-- ---------------------------------------------------------------------------
alter table public.ai_interview_rubric_criteria enable row level security;
alter table public.ai_interview_scores enable row level security;

-- Recruiters read the rubric, including the global template. Editing weights is
-- a deliberate act with scoring consequences and goes through the backend, in
-- the same posture project 01 settled on for ICP weights.
drop policy if exists ai_rubric_select on public.ai_interview_rubric_criteria;
create policy ai_rubric_select on public.ai_interview_rubric_criteria
  for select using (organization_id is null or public.is_org_member(organization_id));

-- Read-only, for the same reason turns are: a recruiter who could write a score
-- row could write its evidence quote too, and the evidence check is the whole
-- point of this migration.
drop policy if exists ai_scores_select on public.ai_interview_scores;
create policy ai_scores_select on public.ai_interview_scores
  for select using (public.is_org_member(organization_id));

-- ---------------------------------------------------------------------------
-- Global default rubric
-- ---------------------------------------------------------------------------
-- Five criteria, max 5 each, weighted total 27. Written to be answerable from
-- what a candidate actually says in five turns — nothing here can be scored
-- from a resume, which is the point of running the interview at all.
insert into public.ai_interview_rubric_criteria
  (organization_id, role_id, criterion_key, label, description, weight, max_score, display_order)
values
  (null, null, 'relevant_experience', 'Relevant experience',
   'Has the candidate done work of this kind before? Look for named systems, scale, and their actual part in it — not familiarity with the words.',
   2.0, 5, 10),
  (null, null, 'depth_of_reasoning', 'Depth of reasoning',
   'Do they explain why, not just what? Look for a tradeoff considered and rejected, a constraint that shaped the decision, or a reason the obvious approach was wrong.',
   2.0, 5, 20),
  (null, null, 'concrete_ownership', 'Concrete ownership',
   'Is the contribution specific and first-person? "I" with a verifiable detail scores; "we" with a generic outcome does not.',
   1.5, 5, 30),
  (null, null, 'communication_clarity', 'Communication clarity',
   'Is the answer structured and readable by someone who was not there? Reward precision and brevity, not length.',
   1.0, 5, 40),
  (null, null, 'failure_and_learning', 'Failure and learning',
   'Can they describe something that went wrong, their part in it, and what changed afterwards? A candidate with no failures has not been near anything hard.',
   1.0, 5, 50)
on conflict do nothing;
