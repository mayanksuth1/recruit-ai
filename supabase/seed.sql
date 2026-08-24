-- Local-development seed. Runs only against the local stack (supabase start /
-- supabase db reset); it is never applied to a hosted project and is not part
-- of setup-database.sql.
--
-- Why this exists: hosted Supabase projects grant anon/authenticated/
-- service_role full DML on public tables by default, so the migrations never
-- had to say so. The local images narrowed that default to Dxtm (no
-- select/insert/update), which makes every PostgREST call fail with 42501.
-- Re-granting here reproduces hosted behaviour. RLS still does the real work —
-- every table's policy checks is_org_member(organization_id).

grant usage on schema public to anon, authenticated, service_role;

grant all privileges on all tables    in schema public to anon, authenticated, service_role;
grant all privileges on all sequences in schema public to anon, authenticated, service_role;
grant execute on all functions        in schema public to anon, authenticated, service_role;

alter default privileges in schema public
  grant all privileges on tables to anon, authenticated, service_role;
alter default privileges in schema public
  grant all privileges on sequences to anon, authenticated, service_role;
alter default privileges in schema public
  grant execute on functions to anon, authenticated, service_role;
