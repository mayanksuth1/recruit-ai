-- OPTIONAL convenience helper — read before running.
--
-- Applying migrations requires DDL, which the service key alone cannot do
-- through Supabase's REST API. This function lets the service key execute
-- SQL via RPC so future phase migrations (0003+) can be applied
-- automatically instead of you pasting each one into the SQL editor.
--
-- Trade-off: anyone holding the service SECRET key gains full DDL power over
-- this database (they already have full read/write on all data). If you'd
-- rather keep applying migrations by hand, simply don't run this file —
-- everything else works without it.
--
-- To remove later:  drop function public.admin_exec_sql(text);

create or replace function public.admin_exec_sql(sql text)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  if coalesce(auth.role(), '') is distinct from 'service_role' then
    raise exception 'forbidden: service role required';
  end if;
  execute sql;
end;
$$;

revoke all on function public.admin_exec_sql(text) from public;
revoke all on function public.admin_exec_sql(text) from anon;
revoke all on function public.admin_exec_sql(text) from authenticated;
grant execute on function public.admin_exec_sql(text) to service_role;
