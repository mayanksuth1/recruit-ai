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
