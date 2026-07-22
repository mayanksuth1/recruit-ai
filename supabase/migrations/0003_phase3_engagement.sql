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
