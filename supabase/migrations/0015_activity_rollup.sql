-- 0015: keep activity history permanently, as daily totals.
--
-- Detailed activity_log rows expire (ACTIVITY_RETENTION_DAYS, default 365),
-- because a per-person action trail should not be kept forever. Before a row
-- is deleted it is folded into activity_daily: one row per day, workspace and
-- action with how many times it happened and by how many distinct users.
-- Those totals carry no user ids and are kept indefinitely, so growth and
-- usage history survives every purge.
--
-- Rollup and delete happen in ONE statement, inside one transaction: a row is
-- never deleted without having been counted, and never counted twice.

create table if not exists public.activity_daily (
  day             date not null,
  organization_id uuid references public.organizations(id) on delete set null,
  action          text not null,
  events          integer not null default 0,
  users           integer not null default 0
);

-- organization_id may be NULL (actions with no workspace, or a deleted one),
-- so uniqueness goes through a coalesce rather than a plain primary key.
create unique index if not exists activity_daily_key
  on public.activity_daily (day, coalesce(organization_id, '00000000-0000-0000-0000-000000000000'::uuid), action);

alter table public.activity_daily enable row level security;
revoke all on public.activity_daily from anon, authenticated;
grant all on public.activity_daily to service_role;


create or replace function public.activity_rollup_and_purge(p_before timestamptz)
returns integer
language sql
as $$
  with expired as (
    delete from public.activity_log
     where created_at < p_before
    returning created_at, organization_id, user_id, action
  ),
  totals as (
    select (created_at at time zone 'utc')::date as day, organization_id, action,
           count(*)::int as events, count(distinct user_id)::int as users
      from expired
     group by 1, 2, 3
  ),
  folded as (
    insert into public.activity_daily as d (day, organization_id, action, events, users)
    select day, organization_id, action, events, users from totals
    on conflict (day, coalesce(organization_id, '00000000-0000-0000-0000-000000000000'::uuid), action)
    do update set events = d.events + excluded.events,
                  -- distinct users cannot be merged exactly across batches;
                  -- the larger count is the honest lower bound.
                  users  = greatest(d.users, excluded.users)
    returning 1
  )
  select count(*)::int from expired;
$$;

revoke execute on function public.activity_rollup_and_purge(timestamptz) from public, anon, authenticated;
grant  execute on function public.activity_rollup_and_purge(timestamptz) to service_role;
