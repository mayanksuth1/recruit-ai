-- Local-development seed. Runs only against the local stack (supabase start /
-- supabase db reset), AFTER every migration; it is never applied to a hosted
-- project and is not part of setup-database.sql.
--
-- Why this exists: the local images do not grant service_role DML on public
-- tables the way hosted projects do, and without it every backend call fails
-- with 42501 permission denied.
--
-- Only service_role is granted. This file used to grant anon and
-- authenticated everything as well, which re-opened every table (and
-- admin_exec_sql) to anyone holding the public anon key, undoing the
-- revokes in 0000 and 0012. The browser never needs table access: it uses
-- Supabase for sign-in only and reaches data through the backend.

grant usage on schema public to service_role;

grant all privileges on all tables    in schema public to service_role;
grant all privileges on all sequences in schema public to service_role;
grant execute on all functions        in schema public to service_role;

alter default privileges in schema public
  grant all privileges on tables to service_role;
alter default privileges in schema public
  grant all privileges on sequences to service_role;
alter default privileges in schema public
  grant execute on functions to service_role;
