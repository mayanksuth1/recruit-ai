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
