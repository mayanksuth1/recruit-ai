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
