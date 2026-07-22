-- ============================================================
-- RECRUIT AI - DATABASE SETUP (run ONCE in the Supabase SQL Editor)
-- Paste this entire file and click RUN.
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
