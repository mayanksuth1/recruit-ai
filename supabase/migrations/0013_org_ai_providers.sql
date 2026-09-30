-- 0013: bring-your-own AI provider, plus a metered free allowance.
--
-- Each organization may connect its own model provider (OpenAI, Anthropic,
-- Gemini, Groq, OpenRouter, any OpenAI-compatible endpoint...). Every AI
-- feature in that workspace then runs on the organization's key. Without one,
-- the workspace runs on the platform's key up to a monthly allowance counted
-- in ai_usage.
--
-- The API key is stored ENCRYPTED by the backend (Fernet, key held only in the
-- backend's environment), so a database dump alone does not leak it. Only the
-- last four characters are kept in the clear, for display.
--
-- Neither table is reachable by the public API roles (see 0012): no grants to
-- anon/authenticated and no RLS policies. Only the backend's service role
-- touches them.

create table if not exists public.org_ai_providers (
  organization_id    uuid primary key references public.organizations(id) on delete cascade,
  provider           text not null,
  base_url           text not null,
  model              text not null,
  quality_model      text,
  api_key_ciphertext text not null,
  key_last4          text not null,
  updated_by         uuid references auth.users(id) on delete set null,
  updated_at         timestamptz not null default now()
);

alter table public.org_ai_providers enable row level security;

create table if not exists public.ai_usage (
  organization_id uuid not null references public.organizations(id) on delete cascade,
  month           date not null,           -- first day of the month, UTC
  platform_calls  integer not null default 0,
  primary key (organization_id, month)
);

alter table public.ai_usage enable row level security;

-- Atomic check-and-count: two concurrent requests cannot both slip under the
-- limit, which a read-then-write from the backend would allow.
create or replace function public.ai_usage_bump(p_org uuid, p_month date)
returns integer
language sql
as $$
  insert into public.ai_usage (organization_id, month, platform_calls)
  values (p_org, p_month, 1)
  on conflict (organization_id, month)
  do update set platform_calls = public.ai_usage.platform_calls + 1
  returning platform_calls;
$$;

revoke all on public.org_ai_providers from anon, authenticated;
revoke all on public.ai_usage         from anon, authenticated;
revoke execute on function public.ai_usage_bump(uuid, date) from public, anon, authenticated;

grant all on public.org_ai_providers to service_role;
grant all on public.ai_usage         to service_role;
grant execute on function public.ai_usage_bump(uuid, date) to service_role;
