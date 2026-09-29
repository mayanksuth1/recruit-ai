-- 0012: take direct database access away from the public API roles.
--
-- The browser holds the anon key and a user JWT, and until now both could
-- read and write every table in `public` straight through PostgREST, limited
-- only by RLS. RLS confines a caller to their own organization, but not to
-- the operations the product allows: a recruiter could PATCH a candidate to
-- 'offer' past approval gate 2, rewrite a draft's recipient and then send it,
-- or repoint an interview at someone else's calendar.
--
-- Nothing legitimate uses that path. The frontend talks to Supabase for
-- sign-in only; every data read and write goes through the FastAPI backend,
-- which uses the service role and enforces the gates. So the public roles get
-- nothing here, and the backend is the only door. RLS policies stay in place
-- as a second layer should a grant ever creep back.
--
-- Functions matter as much as tables: Postgres grants EXECUTE to PUBLIC by
-- default, which is how admin_exec_sql (0000) stayed callable by anon.

revoke all privileges on all tables    in schema public from anon, authenticated;
revoke all privileges on all sequences in schema public from anon, authenticated;
revoke execute on all functions        in schema public from public, anon, authenticated;

-- Future objects created by the migration role start closed too.
alter default privileges in schema public
  revoke all privileges on tables from anon, authenticated;
alter default privileges in schema public
  revoke all privileges on sequences from anon, authenticated;
alter default privileges in schema public
  revoke execute on functions from public, anon, authenticated;

-- The backend needs all of it.
grant usage on schema public to service_role;
grant all privileges on all tables    in schema public to service_role;
grant all privileges on all sequences in schema public to service_role;
grant execute on all functions        in schema public to service_role;
