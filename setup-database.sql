-- ============================================================
-- RECRUIT AI - DATABASE SETUP (run ONCE in the Supabase SQL Editor)
-- Paste this entire file and click RUN.
--
-- Covers phases 1-9, including the Level 2 async AI interviews, rubric
-- evidence checking and pgvector semantic search.
--
-- GENERATED FILE - do not edit by hand.
-- Source: supabase/migrations/*.sql
-- Rebuild: node scripts/build_setup_sql.mjs
-- ============================================================

-- ------------------ 0001_phase1_foundation.sql ------------------
-- Phase 1: Foundation — organizations, membership, roles, candidates, scores
-- All tenant tables carry organization_id and are protected by RLS.
-- Run this in the Supabase SQL editor (or via psql / supabase db push).

create extension if not exists "pgcrypto";

-- ---------------------------------------------------------------------------
-- Tenancy
-- ---------------------------------------------------------------------------
create table if not exists public.organizations (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  plan_tier text not null default 'starter',
  created_at timestamptz not null default now()
);

create table if not exists public.organization_members (
  organization_id uuid not null references public.organizations(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  member_role text not null default 'recruiter', -- 'owner' | 'recruiter'
  created_at timestamptz not null default now(),
  primary key (organization_id, user_id)
);

-- Helper: does the current authenticated user belong to the given org?
create or replace function public.is_org_member(org_id uuid)
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1 from public.organization_members m
    where m.organization_id = org_id and m.user_id = auth.uid()
  );
$$;

-- ---------------------------------------------------------------------------
-- Domain tables
-- ---------------------------------------------------------------------------
create table if not exists public.roles (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  title text not null,
  description text not null default '',       -- the job description used for scoring
  status text not null default 'open',        -- 'open' | 'closed'
  created_by uuid references auth.users(id),
  created_at timestamptz not null default now()
);

create table if not exists public.candidates (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  role_id uuid references public.roles(id) on delete set null,
  full_name text not null,
  email text,
  phone text,
  resume_text text,                            -- extracted text from PDF
  source text not null default 'upload',       -- 'upload' | 'csv_import' | 'manual'
  shortlist_status text not null default 'pending', -- 'pending' | 'approved' | 'rejected'
  created_at timestamptz not null default now()
);

create table if not exists public.scores (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  candidate_id uuid not null references public.candidates(id) on delete cascade,
  role_id uuid not null references public.roles(id) on delete cascade,
  overall_score numeric not null,              -- 0-100
  skills_score numeric,
  experience_score numeric,
  education_score numeric,
  rationale text,                              -- model explanation
  model text,                                  -- which model produced it
  created_at timestamptz not null default now(),
  unique (candidate_id, role_id)
);

create index if not exists idx_roles_org on public.roles(organization_id);
create index if not exists idx_candidates_org on public.candidates(organization_id);
create index if not exists idx_candidates_role on public.candidates(role_id);
create index if not exists idx_scores_org on public.scores(organization_id);
create index if not exists idx_scores_role on public.scores(role_id);

-- ---------------------------------------------------------------------------
-- Row Level Security
-- ---------------------------------------------------------------------------
alter table public.organizations enable row level security;
alter table public.organization_members enable row level security;
alter table public.roles enable row level security;
alter table public.candidates enable row level security;
alter table public.scores enable row level security;

-- organizations: members can read their own org; creation happens via backend
-- (service role bypasses RLS for the bootstrap step).
drop policy if exists org_select on public.organizations;
create policy org_select on public.organizations
  for select using (public.is_org_member(id));

-- organization_members: a user can see their own memberships and those of
-- orgs they belong to.
drop policy if exists members_select on public.organization_members;
create policy members_select on public.organization_members
  for select using (user_id = auth.uid() or public.is_org_member(organization_id));

-- Tenant tables: full CRUD for members of the owning org, nothing otherwise.
drop policy if exists roles_all on public.roles;
create policy roles_all on public.roles
  for all using (public.is_org_member(organization_id))
  with check (public.is_org_member(organization_id));

drop policy if exists candidates_all on public.candidates;
create policy candidates_all on public.candidates
  for all using (public.is_org_member(organization_id))
  with check (public.is_org_member(organization_id));

drop policy if exists scores_all on public.scores;
create policy scores_all on public.scores
  for all using (public.is_org_member(organization_id))
  with check (public.is_org_member(organization_id));

-- ------------------ 0002_phase2_sourcing.sql ------------------
-- Phase 2: Sourcing + Screening — talent pool (org-wide candidates that
-- persist across roles), link from role-specific candidates to pool entries.
-- Run in the Supabase SQL editor.

create table if not exists public.talent_pool (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  full_name text not null,
  email text,                                  -- stored lowercased; used for dedup on import
  phone text,
  location text,
  current_title text,
  current_company text,
  years_experience numeric,
  skills text,                                 -- comma-separated
  profile_text text,                           -- resume text or composed CSV summary
  source text not null default 'csv_import',   -- 'csv_import' | 'paste_import' | 'resume_upload' | 'manual'
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_talent_pool_org on public.talent_pool(organization_id);
create unique index if not exists uq_talent_pool_org_email
  on public.talent_pool(organization_id, email) where email is not null;

-- Role-specific candidate records now link back to their pool entry.
alter table public.candidates
  add column if not exists talent_pool_id uuid references public.talent_pool(id) on delete set null;

alter table public.talent_pool enable row level security;

drop policy if exists talent_pool_all on public.talent_pool;
create policy talent_pool_all on public.talent_pool
  for all using (public.is_org_member(organization_id))
  with check (public.is_org_member(organization_id));

-- ------------------ 0003_phase3_engagement.sql ------------------
-- Phase 3: Engagement — reviewed-before-send message queue + candidate stages.
-- Every message is created as a DRAFT; only an explicit human action
-- (POST /messages/{id}/send) moves it to sent. Nothing is auto-sent.

alter table public.candidates
  add column if not exists stage text not null default 'screening';
-- stage: 'screening' | 'outreach' | 'interview' | 'offer' | 'closed'

create table if not exists public.messages (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  candidate_id uuid not null references public.candidates(id) on delete cascade,
  role_id uuid references public.roles(id) on delete set null,
  kind text not null default 'outreach',      -- 'outreach' | 'status_update' | 'follow_up'
  to_email text not null,
  subject text not null,
  body text not null,
  status text not null default 'draft',       -- 'draft' | 'sent' | 'discarded'
  parent_message_id uuid references public.messages(id) on delete set null,
  provider_id text,                            -- Resend email id once sent
  error text,
  responded_at timestamptz,                    -- recruiter marks candidate reply
  created_by uuid references auth.users(id),
  sent_by uuid references auth.users(id),
  created_at timestamptz not null default now(),
  sent_at timestamptz
);

create index if not exists idx_messages_org on public.messages(organization_id);
create index if not exists idx_messages_candidate on public.messages(candidate_id);
create index if not exists idx_messages_status on public.messages(organization_id, status);

alter table public.messages enable row level security;

drop policy if exists messages_all on public.messages;
create policy messages_all on public.messages
  for all using (public.is_org_member(organization_id))
  with check (public.is_org_member(organization_id));

-- ------------------ 0004_phase4_scheduling.sql ------------------
-- Phase 4: Scheduling — per-recruiter Google Calendar connections, interviews
-- with candidate-facing scheduling links, reminder/nudge bookkeeping.

create table if not exists public.calendar_connections (
  user_id uuid primary key references auth.users(id) on delete cascade,
  organization_id uuid not null references public.organizations(id) on delete cascade,
  google_email text,
  access_token text not null,
  refresh_token text,
  token_expires_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.calendar_connections enable row level security;
-- Tokens are sensitive: owner-only visibility (backend uses service role).
drop policy if exists calconn_own on public.calendar_connections;
create policy calconn_own on public.calendar_connections
  for select using (user_id = auth.uid());

-- Short-lived OAuth state nonces; service-role only (RLS on, no policies).
create table if not exists public.oauth_states (
  state text primary key,
  user_id uuid not null,
  organization_id uuid not null,
  created_at timestamptz not null default now()
);
alter table public.oauth_states enable row level security;

create table if not exists public.interviews (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  candidate_id uuid not null references public.candidates(id) on delete cascade,
  role_id uuid references public.roles(id) on delete set null,
  interviewer_user_id uuid references auth.users(id),
  interviewer_email text,
  attendee_emails text[] not null default '{}',
  duration_minutes int not null default 45,
  proposed_slots jsonb,                        -- [{"start": iso, "end": iso}, ...]
  public_token uuid unique not null default gen_random_uuid(),
  scheduled_start timestamptz,
  scheduled_end timestamptz,
  google_event_id text,
  meet_link text,
  status text not null default 'proposed',     -- 'proposed' | 'scheduled' | 'completed' | 'cancelled'
  feedback text,
  feedback_logged_at timestamptz,
  reminder_drafted_at timestamptz,             -- 24h-before reminder draft created
  nudge_sent_at timestamptz,                   -- 48h-after feedback nudge sent to interviewer
  created_at timestamptz not null default now()
);

create index if not exists idx_interviews_org on public.interviews(organization_id);
create index if not exists idx_interviews_candidate on public.interviews(candidate_id);
create index if not exists idx_interviews_status on public.interviews(organization_id, status);

alter table public.interviews enable row level security;
drop policy if exists interviews_all on public.interviews;
create policy interviews_all on public.interviews
  for all using (public.is_org_member(organization_id))
  with check (public.is_org_member(organization_id));

-- ------------------ 0005_phase5_ats_sync.sql ------------------
-- Phase 5: Human approval gate 2 (offer/closure) + generic webhook ATS sync.

-- Gate 2: moving a candidate to 'offer' or 'closed' requires an explicit,
-- recorded approval — same pattern as gate 1 (shortlist approval).
alter table public.candidates
  add column if not exists offer_approved_at timestamptz,
  add column if not exists offer_approved_by uuid references auth.users(id);

-- One generic connection per org: outbound URL we POST events to (any ATS
-- that accepts webhooks — Greenhouse/Lever style), inbound token the ATS
-- uses to push events to us. Workday-class integrations need their paid
-- enterprise API tier and are out of scope here.
create table if not exists public.ats_connections (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade unique,
  name text not null default 'default',
  outbound_url text,
  secret text,                                  -- HMAC-SHA256 signing key (both directions)
  inbound_token uuid unique not null default gen_random_uuid(),
  active boolean not null default true,
  created_at timestamptz not null default now()
);

create table if not exists public.ats_events (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  connection_id uuid references public.ats_connections(id) on delete set null,
  direction text not null,                      -- 'outbound' | 'inbound'
  event_type text,
  candidate_id uuid references public.candidates(id) on delete set null,
  payload jsonb,
  result text,                                  -- 'delivered' | 'failed' | 'applied' | 'rejected'
  detail text,
  created_at timestamptz not null default now()
);

create index if not exists idx_ats_events_org on public.ats_events(organization_id, created_at desc);

alter table public.ats_connections enable row level security;
alter table public.ats_events enable row level security;

drop policy if exists ats_conn_all on public.ats_connections;
create policy ats_conn_all on public.ats_connections
  for all using (public.is_org_member(organization_id))
  with check (public.is_org_member(organization_id));

drop policy if exists ats_events_select on public.ats_events;
create policy ats_events_select on public.ats_events
  for select using (public.is_org_member(organization_id));

-- ------------------ 0006_phase6_reporting.sql ------------------
-- Phase 6: Reporting — stored weekly summaries (rendered to PDF on demand).

create table if not exists public.reports (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  kind text not null default 'weekly',
  period_start date not null,
  period_end date not null,
  data jsonb not null,                          -- metrics snapshot at generation time
  created_at timestamptz not null default now(),
  unique (organization_id, kind, period_start)
);

create index if not exists idx_reports_org on public.reports(organization_id, created_at desc);

alter table public.reports enable row level security;

drop policy if exists reports_select on public.reports;
create policy reports_select on public.reports
  for select using (public.is_org_member(organization_id));

-- ------------------ 0007_l2_ai_interviews.sql ------------------
-- Phase 7 (Level 2): asynchronous AI interviews.
--
-- `interviews` (0004) already means a calendar-scheduled interview with a human
-- interviewer. This is a different thing — a candidate answering an AI on their
-- own time, from a single-use link — so it gets its own tables rather than more
-- nullable columns on that one.
--
-- Two guarantees are built into the schema rather than the application:
--
--   1. One token can only ever produce one session. The session row is created
--      AT ISSUE TIME and the token hash is UNIQUE on it, so "start a second
--      session" is not a check that can be raced past — there is no second row
--      to create.
--
--   2. The transcript is append-only. A question is immutable once asked, an
--      answer is immutable once given. Level 2 scores each rubric criterion
--      against a verbatim quote from this transcript; if the transcript could
--      be edited afterwards, a validated quote could silently stop matching and
--      the evidence check would be theatre.

-- ---------------------------------------------------------------------------
-- Token hashing
-- ---------------------------------------------------------------------------
-- The raw token is never stored. It is generated by the backend, handed to the
-- candidate once inside the link, and only its SHA-256 lands in the database.
--
-- This deliberately departs from `interviews.public_token`, which stores its
-- token in the clear. There the token only selects a time slot. Here the token
-- IS the authentication — it opens a live interview and everything the
-- candidate has already said — and recruiters can SELECT this table. A stored
-- plaintext token would let any org member resume any candidate's interview as
-- that candidate.
--
-- sha256() and convert_to() are both core PostgreSQL; no pgcrypto dependency,
-- so this resolves the same whether pgcrypto lives in `public` or `extensions`.
create or replace function public.ai_interview_token_hash(raw_token text)
  returns bytea language sql immutable strict
as $fn$
  select sha256(convert_to(raw_token, 'utf8'))
$fn$;

comment on function public.ai_interview_token_hash(text) is
  'SHA-256 of an interview link token. The backend hashes with hashlib.sha256(t.encode()).digest() — identical bytes.';

-- Legal status transitions, in one place so the guard trigger and any future
-- reader agree on what the lifecycle is.
--
--   issued           link handed out, nothing asked yet
--   in_progress      Q1 exists — the token is spent, the session is live
--   completed        every question answered; scoring may now run
--   scoring_rejected scoring ran and at least one evidence quote failed
--   scored           scoring ran and every quote matched the transcript
--
-- There is no 'expired' status. Expiry is `expires_at < now()` and is read, not
-- written — a stored flag would need a sweeper and would drift from the column
-- it duplicates. `scored` is terminal: once a valid score card exists, a later
-- bad re-score cannot demolish it.
create or replace function public.ai_interview_next_states(from_status text)
  returns text[] language sql immutable
as $fn$
  select case from_status
    when 'issued'           then array['in_progress']
    when 'in_progress'      then array['completed']
    when 'completed'        then array['scored', 'scoring_rejected']
    when 'scoring_rejected' then array['scored']
    else array[]::text[]
  end
$fn$;

-- ---------------------------------------------------------------------------
-- Sessions
-- ---------------------------------------------------------------------------
create table if not exists public.ai_interview_sessions (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references public.organizations(id) on delete cascade,
  candidate_id uuid not null references public.candidates(id) on delete cascade,
  role_id uuid references public.roles(id) on delete set null,

  token_hash bytea not null unique,            -- SHA-256; the raw token is not stored
  issued_at timestamptz not null default now(),
  expires_at timestamptz not null default (now() + interval '72 hours'),
  consumed_at timestamptz,                     -- stamped when Q1 is written; write-once

  status text not null default 'issued',
  question_target int not null default 5,
  completed_at timestamptz,

  issued_by uuid references auth.users(id),
  created_at timestamptz not null default now(),

  constraint ai_sessions_status_check check (status in
    ('issued', 'in_progress', 'completed', 'scored', 'scoring_rejected')),
  constraint ai_sessions_target_check check (question_target between 1 and 20),
  constraint ai_sessions_window_check check (expires_at > issued_at)
);

create index if not exists idx_ai_sessions_org on public.ai_interview_sessions(organization_id);
create index if not exists idx_ai_sessions_candidate on public.ai_interview_sessions(candidate_id);
create index if not exists idx_ai_sessions_status on public.ai_interview_sessions(organization_id, status);

comment on column public.ai_interview_sessions.consumed_at is
  'When the token produced its first question. Consumption stops a SECOND session being minted; it does not stop this one resuming.';

-- ---------------------------------------------------------------------------
-- Turns
-- ---------------------------------------------------------------------------
-- One row per question. The question is written when it is generated and
-- BEFORE it is shown; the answer arrives later as an UPDATE. That ordering is
-- what makes a crash survivable: whatever the candidate saw is already on
-- record, so reopening the link re-serves the same question rather than
-- generating a different one and quietly rewriting history.
create table if not exists public.ai_interview_turns (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null,               -- copied from the session by the gate trigger
  session_id uuid not null references public.ai_interview_sessions(id) on delete cascade,
  ordinal int not null,

  question_text text not null,
  asked_at timestamptz not null default now(),
  answer_text text,
  answered_at timestamptz,

  -- Provenance for DONE #4: which turn's answer this question was conditioned
  -- on, and what the model saw. Q1 has no source turn.
  source_turn_ordinal int,
  model text,

  constraint ai_turns_ordinal_check check (ordinal >= 1),
  constraint ai_turns_source_check check (source_turn_ordinal is null or source_turn_ordinal < ordinal)
);

-- The idempotency key. A double-submitted question or a duplicated request
-- collides here instead of forking the transcript.
create unique index if not exists uq_ai_turns_session_ordinal
  on public.ai_interview_turns(session_id, ordinal);
create index if not exists idx_ai_turns_org on public.ai_interview_turns(organization_id);

-- ---------------------------------------------------------------------------
-- Session guard
-- ---------------------------------------------------------------------------
create or replace function public.ai_interview_sessions_guard()
  returns trigger language plpgsql
as $fn$
begin
  if new.token_hash is distinct from old.token_hash then
    raise exception 'ai_interview_sessions: token_hash is immutable — issue a new session instead';
  end if;

  if new.organization_id is distinct from old.organization_id
     or new.candidate_id is distinct from old.candidate_id
     or new.role_id is distinct from old.role_id then
    raise exception 'ai_interview_sessions: a session cannot be reassigned to another tenant, candidate or role';
  end if;

  if old.consumed_at is not null and new.consumed_at is distinct from old.consumed_at then
    raise exception 'ai_interview_sessions: consumed_at is write-once (already %)', old.consumed_at;
  end if;

  if new.question_target is distinct from old.question_target and old.consumed_at is not null then
    raise exception 'ai_interview_sessions: the question count is fixed once the interview has started';
  end if;

  -- expires_at stays mutable ON PURPOSE. build.md DONE #2 is verified by
  -- backdating it on a real session row; a trigger that froze it would make
  -- the expiry path untestable without inserting a fake session.
  --
  -- Note for anyone doing that: ai_sessions_window_check is `expires_at >
  -- issued_at`, so expires_at CANNOT be dragged into the past on its own —
  -- issued_at has to move with it. Backdate the whole window (issued_at =
  -- now() - 80h, expires_at = now() - 8h), which is what an expired link
  -- actually is anyway. issued_at is left mutable for exactly this reason.

  if new.status is distinct from old.status
     and not (new.status = any (public.ai_interview_next_states(old.status))) then
    raise exception 'ai_interview_sessions: illegal transition % -> % (session %)',
      old.status, new.status, old.id;
  end if;

  return new;
end
$fn$;

drop trigger if exists ai_sessions_guard on public.ai_interview_sessions;
create trigger ai_sessions_guard before update on public.ai_interview_sessions
  for each row execute function public.ai_interview_sessions_guard();

-- ---------------------------------------------------------------------------
-- Turn gate
-- ---------------------------------------------------------------------------
create or replace function public.ai_interview_turns_gate()
  returns trigger language plpgsql
as $fn$
declare
  s public.ai_interview_sessions%rowtype;
  prev public.ai_interview_turns%rowtype;
begin
  -- FOR UPDATE serialises concurrent writes against one session, so two
  -- simultaneous submissions cannot both pass the "previous turn is answered"
  -- test below. The unique index on (session_id, ordinal) is the second line
  -- of defence, not the first.
  select * into s from public.ai_interview_sessions
    where id = coalesce(new.session_id, old.session_id)
    for update;
  if not found then
    raise exception 'ai_interview_turns: session % does not exist', new.session_id;
  end if;

  if tg_op = 'INSERT' then
    -- Never trust a caller-supplied tenant on a table whose RLS depends on it.
    new.organization_id := s.organization_id;

    if s.expires_at <= now() then
      raise exception 'ai_interview_turns: session % expired at %', s.id, s.expires_at;
    end if;
    if s.status not in ('issued', 'in_progress') then
      raise exception 'ai_interview_turns: session % is %, not accepting questions', s.id, s.status;
    end if;
    if new.ordinal > s.question_target then
      raise exception 'ai_interview_turns: ordinal % exceeds question_target % for session %',
        new.ordinal, s.question_target, s.id;
    end if;
    if btrim(coalesce(new.question_text, '')) = '' then
      raise exception 'ai_interview_turns: a turn must carry its question text';
    end if;
    -- The question is recorded before it is shown. Supplying the answer in the
    -- same statement would mean the question was never on record on its own,
    -- which is precisely the crash window this design closes.
    if new.answer_text is not null then
      raise exception 'ai_interview_turns: insert the question first, then answer it with an UPDATE';
    end if;
    new.answered_at := null;

    if new.ordinal > 1 then
      select * into prev from public.ai_interview_turns
        where session_id = new.session_id and ordinal = new.ordinal - 1;
      if not found then
        raise exception 'ai_interview_turns: turn % cannot exist before turn %',
          new.ordinal, new.ordinal - 1;
      end if;
      if prev.answer_text is null then
        raise exception 'ai_interview_turns: turn % is unanswered — question % is not due yet',
          prev.ordinal, new.ordinal;
      end if;
    end if;

    return new;
  end if;

  -- UPDATE ------------------------------------------------------------------
  if new.session_id is distinct from old.session_id
     or new.ordinal is distinct from old.ordinal then
    raise exception 'ai_interview_turns: a turn cannot be moved to another session or ordinal';
  end if;
  if new.question_text is distinct from old.question_text then
    raise exception 'ai_interview_turns: the question is immutable once asked';
  end if;
  new.organization_id := old.organization_id;
  new.asked_at := old.asked_at;

  if old.answer_text is not null then
    if new.answer_text is distinct from old.answer_text then
      raise exception 'ai_interview_turns: turn % of session % is already answered; the transcript is append-only',
        old.ordinal, old.session_id;
    end if;
    new.answered_at := old.answered_at;
    return new;
  end if;

  if new.answer_text is not null then
    if btrim(new.answer_text) = '' then
      raise exception 'ai_interview_turns: a blank answer is not an answer';
    end if;
    if s.expires_at <= now() then
      raise exception 'ai_interview_turns: session % expired at % — the answer window has closed',
        s.id, s.expires_at;
    end if;
    new.answered_at := now();
  end if;

  return new;
end
$fn$;

drop trigger if exists ai_turns_gate on public.ai_interview_turns;
create trigger ai_turns_gate before insert or update on public.ai_interview_turns
  for each row execute function public.ai_interview_turns_gate();

-- ---------------------------------------------------------------------------
-- Session advancement — the application never sets these by hand
-- ---------------------------------------------------------------------------
create or replace function public.ai_interview_advance_session()
  returns trigger language plpgsql
as $fn$
declare
  target int;
  answered int;
begin
  if tg_op = 'INSERT' then
    -- Writing Q1 is what spends the token. Defining consumption as a
    -- side effect of the first question — rather than a separate flag the
    -- backend has to remember to set — means a link cannot be half-consumed.
    update public.ai_interview_sessions
       set consumed_at = coalesce(consumed_at, now()),
           status = case when status = 'issued' then 'in_progress' else status end
     where id = new.session_id;
    return null;
  end if;

  if new.answer_text is null then
    return null;
  end if;

  select question_target into target
    from public.ai_interview_sessions where id = new.session_id;
  select count(*) into answered
    from public.ai_interview_turns
   where session_id = new.session_id and answer_text is not null;

  if answered >= target then
    update public.ai_interview_sessions
       set status = 'completed', completed_at = now()
     where id = new.session_id and status = 'in_progress';
  end if;

  return null;
end
$fn$;

drop trigger if exists ai_turns_advance on public.ai_interview_turns;
create trigger ai_turns_advance after insert or update of answer_text
  on public.ai_interview_turns
  for each row execute function public.ai_interview_advance_session();

-- ---------------------------------------------------------------------------
-- Reading the session
-- ---------------------------------------------------------------------------
-- Resume state, computed. Turns are strictly sequential and only the last one
-- can be unanswered, so the next ordinal is always answered_count + 1 — whether
-- the candidate is resuming a question they already saw or waiting on one that
-- has yet to be generated. `next_question_text` distinguishes the two: non-null
-- means re-serve exactly this, null means generate it.
create or replace view public.ai_interview_session_state
with (security_invoker = on) as
select
  s.id                as session_id,
  s.organization_id,
  s.candidate_id,
  s.role_id,
  s.status,
  s.question_target,
  s.issued_at,
  s.expires_at,
  s.consumed_at,
  s.completed_at,
  (s.expires_at <= now())                       as is_expired,
  t.asked_count,
  t.answered_count,
  case when t.answered_count < s.question_target
       then t.answered_count + 1 end            as next_ordinal,
  t.pending_question                            as next_question_text,
  (s.expires_at > now()
   and s.status in ('issued', 'in_progress'))   as is_open
from public.ai_interview_sessions s
left join lateral (
  select
    count(*)                                            as asked_count,
    count(*) filter (where answer_text is not null)     as answered_count,
    max(question_text) filter (where answer_text is null) as pending_question
  from public.ai_interview_turns where session_id = s.id
) t on true;

-- The candidate's own words, in order. This is the corpus every rubric
-- evidence quote is checked against (0008) and the text that gets embedded as
-- a transcript (0009). Questions are excluded deliberately: a criterion that
-- "proves" itself by quoting the interviewer's own question has proved nothing.
create or replace function public.ai_interview_transcript(p_session uuid)
  returns text language sql stable
as $fn$
  select string_agg(answer_text, E'\n\n' order by ordinal)
    from public.ai_interview_turns
   where session_id = p_session and answer_text is not null
$fn$;

-- ---------------------------------------------------------------------------
-- Row Level Security
-- ---------------------------------------------------------------------------
alter table public.ai_interview_sessions enable row level security;
alter table public.ai_interview_turns enable row level security;

-- Read-only for recruiters, and no write policy at all.
--
-- The candidate is unauthenticated — they hold a token, not a JWT — so every
-- candidate-side read and write goes through the backend's service role keyed
-- by that token, exactly as the existing /api/public/schedule/{token} endpoints
-- do. `authenticated` therefore never needs to write here, and must not: a
-- recruiter who could INSERT or UPDATE a turn could compose a candidate's
-- answer, and every evidence quote on the score card is validated against
-- precisely these rows.
drop policy if exists ai_sessions_select on public.ai_interview_sessions;
create policy ai_sessions_select on public.ai_interview_sessions
  for select using (public.is_org_member(organization_id));

drop policy if exists ai_turns_select on public.ai_interview_turns;
create policy ai_turns_select on public.ai_interview_turns
  for select using (public.is_org_member(organization_id));

-- ------------------ 0008_l2_rubric_scoring.sql ------------------
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

-- ------------------ 0009_l2_pgvector_search.sql ------------------
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

-- ------------------ 0010_company_profile_linkedin_post.sql ------------------
-- Phase 10: Company profile + LinkedIn job-post draft generator.
--
-- Text-only feature: the generated post is copied out by hand. There is no
-- LinkedIn API call, no OAuth, no auto-posting and no image generation
-- anywhere in this migration or the code that reads these columns.

-- ---------------------------------------------------------------------------
-- Company profile — one row per tenant
-- ---------------------------------------------------------------------------
-- Keyed on organization_id with a UNIQUE constraint, exactly as
-- ats_connections is: today that means a single row, and extending to
-- multi-tenant later needs no schema change because every read already
-- filters by org. Columns default to '' rather than being nullable so the
-- GET-then-PUT round trip never has to distinguish null from empty.
create table if not exists public.company_profile (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null unique references public.organizations(id) on delete cascade,
  company_name text not null default '',
  what_we_do text not null default '',        -- what the company actually does
  culture_benefits text not null default '',  -- culture and benefits
  location text not null default '',
  extra_notes text not null default '',       -- "anything else worth telling candidates"
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index if not exists idx_company_profile_org on public.company_profile(organization_id);

alter table public.company_profile enable row level security;

drop policy if exists company_profile_all on public.company_profile;
create policy company_profile_all on public.company_profile
  for all using (public.is_org_member(organization_id))
  with check (public.is_org_member(organization_id));

-- ---------------------------------------------------------------------------
-- The draft itself lives on the role
-- ---------------------------------------------------------------------------
-- One draft per role, edited in place — so a column, not a child table.
-- `scores` earns its own table because it is per (candidate, role); this is
-- a single editable text blob per role with no history requirement.
-- Model and timestamp are recorded the same way scores.model is, so a stale
-- draft can be told apart from a fresh one.
alter table public.roles
  add column if not exists linkedin_post_draft text,
  add column if not exists linkedin_post_model text,
  add column if not exists linkedin_post_generated_at timestamptz;

-- ------------------ 0011_nvidia_embeddings_1024.sql ------------------
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
