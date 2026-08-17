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
