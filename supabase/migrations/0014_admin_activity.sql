-- 0014: platform activity log and the aggregate queries behind /admin.
--
-- The admin dashboard is deliberately metadata-only. It shows WHAT workspaces
-- do and HOW MUCH (counts), never candidate content: no names, emails,
-- phone numbers, resumes, messages or transcripts. Every function below
-- returns counts or account-level fields, so that boundary holds in SQL
-- rather than relying on the frontend not to display something.
--
-- activity_log rows carry an action label (a route template such as
-- "POST /api/roles/{role_id}/linkedin-post"), who, which workspace, when and
-- the HTTP status. No request bodies and no IP addresses. Rows older than
-- 180 days are deleted by the backend's scheduler loop.
--
-- Only the backend's service role can reach any of it (see 0012).

create table if not exists public.activity_log (
  id              bigint generated always as identity primary key,
  created_at      timestamptz not null default now(),
  organization_id uuid references public.organizations(id) on delete cascade,
  user_id         uuid references auth.users(id) on delete set null,
  action          text not null,
  status          integer,
  meta            jsonb not null default '{}'::jsonb
);

create index if not exists activity_log_created_idx on public.activity_log (created_at desc);
create index if not exists activity_log_org_idx     on public.activity_log (organization_id, created_at desc);

alter table public.activity_log enable row level security;
revoke all on public.activity_log from anon, authenticated;
grant all on public.activity_log to service_role;


-- One row per workspace: account fields and counts, nothing else.
create or replace function public.admin_workspace_stats()
returns table (
  organization_id        uuid,
  name                   text,
  plan_tier              text,
  created_at             timestamptz,
  owner_email            text,
  members                bigint,
  roles_total            bigint,
  roles_open             bigint,
  candidates             bigint,
  candidates_by_stage    jsonb,
  resumes_scored         bigint,
  avg_score              numeric,
  pool_size              bigint,
  messages_drafted       bigint,
  messages_sent          bigint,
  messages_replied       bigint,
  interviews_scheduled   bigint,
  interviews_completed   bigint,
  ai_interviews_issued   bigint,
  ai_interviews_done     bigint,
  reports                bigint,
  ai_calls_this_month    integer,
  own_ai_provider        text,
  own_ai_model           text,
  calendar_connected     boolean,
  ats_configured         boolean,
  last_active            timestamptz
)
language sql
stable
security definer
set search_path = public, pg_temp
as $$
  select
    o.id, o.name, o.plan_tier, o.created_at,
    (select u.email::text from organization_members m join auth.users u on u.id = m.user_id
      where m.organization_id = o.id and m.member_role = 'owner' order by m.created_at limit 1),
    (select count(*) from organization_members m where m.organization_id = o.id),
    (select count(*) from roles r where r.organization_id = o.id),
    (select count(*) from roles r where r.organization_id = o.id and r.status = 'open'),
    (select count(*) from candidates c where c.organization_id = o.id),
    (select coalesce(jsonb_object_agg(stage, n), '{}'::jsonb)
       from (select coalesce(c.stage, 'unknown') as stage, count(*) as n
               from candidates c where c.organization_id = o.id group by 1) s),
    (select count(*) from scores s where s.organization_id = o.id),
    (select round(avg(s.overall_score)::numeric, 1) from scores s where s.organization_id = o.id),
    (select count(*) from talent_pool t where t.organization_id = o.id),
    (select count(*) from messages x where x.organization_id = o.id and x.status = 'draft'),
    (select count(*) from messages x where x.organization_id = o.id and x.status = 'sent'),
    (select count(*) from messages x where x.organization_id = o.id and x.responded_at is not null),
    (select count(*) from interviews i where i.organization_id = o.id and i.status = 'scheduled'),
    (select count(*) from interviews i where i.organization_id = o.id and i.feedback_logged_at is not null),
    (select count(*) from ai_interview_sessions a where a.organization_id = o.id),
    (select count(*) from ai_interview_sessions a where a.organization_id = o.id and a.completed_at is not null),
    (select count(*) from reports p where p.organization_id = o.id),
    coalesce((select g.platform_calls from ai_usage g
               where g.organization_id = o.id and g.month = date_trunc('month', now() at time zone 'utc')::date), 0),
    (select p.provider from org_ai_providers p where p.organization_id = o.id),
    (select p.model from org_ai_providers p where p.organization_id = o.id),
    exists (select 1 from calendar_connections k where k.organization_id = o.id),
    exists (select 1 from ats_connections k where k.organization_id = o.id and k.outbound_url is not null),
    (select max(l.created_at) from activity_log l where l.organization_id = o.id)
  from organizations o
  order by o.created_at desc;
$$;


-- Sign-in history from Supabase Auth's own audit trail: event type, account
-- email, time and IP (kept for security review: spotting account attacks).
create or replace function public.admin_auth_events(p_limit integer default 200)
returns table (created_at timestamptz, action text, email text, ip_address text)
language sql
stable
security definer
set search_path = public, pg_temp
as $$
  select e.created_at,
         e.payload->>'action',
         coalesce(e.payload->>'actor_username', e.payload->'traits'->>'user_email'),
         e.ip_address::text
    from auth.audit_log_entries e
   where e.payload->>'action' in ('login', 'logout', 'user_signedup', 'user_recovery_requested',
                                   'user_deleted', 'user_updated_password', 'user_invited')
   order by e.created_at desc
   limit least(greatest(p_limit, 1), 1000);
$$;

revoke execute on function public.admin_workspace_stats()        from public, anon, authenticated;
revoke execute on function public.admin_auth_events(integer)      from public, anon, authenticated;
grant  execute on function public.admin_workspace_stats()        to service_role;
grant  execute on function public.admin_auth_events(integer)      to service_role;
