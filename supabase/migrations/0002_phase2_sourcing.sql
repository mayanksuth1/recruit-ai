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
