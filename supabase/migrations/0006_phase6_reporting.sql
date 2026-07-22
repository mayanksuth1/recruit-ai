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
