-- ============================================================
-- DEMO SEED — 1 role + 7 dummy candidates
--
-- Run in the Supabase SQL editor (it runs as service role, so RLS is
-- bypassed and the inserts land regardless of policy).
--
-- PREREQUISITE: sign up in the app first. Signup is what creates your
-- organization and organization_members row; this script attaches the
-- demo data to that existing org rather than inventing one.
--
-- EDIT the email on the next line to the address you signed up with.
-- ============================================================

do $$
declare
  v_email    text := 'mayanksuth1@gmail.com';   -- <<< CHANGE ME if you signed up with another address
  v_user     uuid;
  v_org      uuid;
  v_role     uuid;
  v_cand     uuid;
  v_pool     uuid;
  r          record;
begin
  select id into v_user from auth.users where lower(email) = lower(v_email);
  if v_user is null then
    raise exception 'No auth user for %. Sign up in the app first, then re-run.', v_email;
  end if;

  select organization_id into v_org
  from public.organization_members
  where user_id = v_user
  order by created_at
  limit 1;

  if v_org is null then
    raise exception 'User % has no organization membership.', v_email;
  end if;

  -- ---------------------------------------------------------------
  -- A role for the candidates to be scored against
  -- ---------------------------------------------------------------
  select id into v_role from public.roles
  where organization_id = v_org and title = 'Senior Backend Engineer'
  limit 1;

  if v_role is null then
    insert into public.roles (organization_id, title, description, status, created_by)
    values (
      v_org,
      'Senior Backend Engineer',
      'We are hiring a senior backend engineer to own our Python/FastAPI services. '
      || 'Must have 5+ years building production APIs, strong PostgreSQL skills, and '
      || 'experience with async workloads, cloud deployment (AWS/GCP) and CI/CD. '
      || 'Nice to have: pgvector / retrieval systems, Kubernetes, and mentoring experience.',
      'open',
      v_user
    )
    returning id into v_role;
  end if;

  -- ---------------------------------------------------------------
  -- 7 dummy candidates, deliberately spread across stages, shortlist
  -- statuses and score bands so every filter in the UI has something
  -- to show.
  -- ---------------------------------------------------------------
  for r in
    select * from (values
      ('Priya Raghavan',   'priya.raghavan@example.com',   '+91 98200 41277',
       'Bengaluru, India',   'Staff Backend Engineer', 'Flipkart',        9.0,
       'Python, FastAPI, PostgreSQL, Kafka, Kubernetes, AWS, pgvector',
       'Nine years building high-throughput commerce APIs. Led the migration of the order service to FastAPI and async SQLAlchemy, cutting p99 latency from 800ms to 120ms. Owns a pgvector-backed product search index serving 40M queries/day. Mentors five engineers.',
       'approved', 'interview', 92, 95, 94, 82,
       'Exceptional match. Exceeds the 5-year bar, deep FastAPI + PostgreSQL ownership, and direct pgvector experience which is a listed nice-to-have. Mentoring experience is a bonus.'),

      ('Daniel Okonkwo',   'daniel.okonkwo@example.com',   '+44 7700 900431',
       'Manchester, UK',     'Senior Software Engineer', 'Monzo',         7.0,
       'Python, Django, PostgreSQL, Terraform, GCP, Celery',
       'Seven years in fintech backends. Built the disputes platform handling 2M events/month on Django and Celery. Strong Postgres tuning background — rewrote the ledger query layer to cut read load by 60%. Terraform-managed GCP infra and full CI/CD ownership.',
       'approved', 'interview', 84, 82, 88, 80,
       'Strong match on experience, PostgreSQL depth and cloud/CI-CD. Primary gap is FastAPI specifically — the async experience is Celery-based rather than ASGI, so some ramp-up expected.'),

      ('Mei-Ling Chen',    'meiling.chen@example.com',     '+1 415 555 0182',
       'San Francisco, USA', 'Backend Engineer', 'Stripe',                6.0,
       'Go, Python, gRPC, PostgreSQL, Kubernetes, AWS',
       'Six years on payments infrastructure, primarily Go with Python tooling. Designed an idempotency layer processing $4B annually. Deep Kubernetes operator experience and on-call leadership for a tier-1 service.',
       'approved', 'outreach', 78, 72, 90, 78,
       'Clears the experience bar comfortably and brings excellent distributed-systems and Kubernetes depth. Python is secondary to Go, so day-to-day FastAPI work would be a shift in primary language.'),

      ('Arjun Mehta',      'arjun.mehta@example.com',      '+91 99010 33845',
       'Pune, India',        'Backend Developer', 'Zoho',                 5.0,
       'Python, FastAPI, MySQL, Redis, Docker, REST',
       'Five years building internal SaaS APIs. Migrated three services from Flask to FastAPI and introduced async request handling. Comfortable with Docker-based deploys, though infrastructure is largely managed by a separate platform team.',
       'pending', 'screening', 71, 78, 66, 72,
       'Meets the minimum 5-year requirement with directly relevant FastAPI migration work. Weaker on PostgreSQL (MySQL background) and has limited hands-on cloud/CI-CD ownership.'),

      ('Sofia Almeida',    'sofia.almeida@example.com',    '+351 912 555 704',
       'Lisbon, Portugal',   'Full Stack Engineer', 'Remote.com',         4.5,
       'TypeScript, Node.js, Python, PostgreSQL, React, AWS',
       'Four and a half years split across frontend and backend. Owns the billing integration service in Node with a Python reporting pipeline. Solid PostgreSQL schema design and AWS Lambda deployment experience.',
       'pending', 'screening', 58, 55, 52, 74,
       'Slightly under the 5-year bar and the experience is split across the stack rather than backend-focused. Good PostgreSQL and AWS signal, but Python is not the primary language.'),

      ('Tomasz Wójcik',    'tomasz.wojcik@example.com',    '+48 512 555 913',
       'Kraków, Poland',     'Java Backend Engineer', 'Allegro',          8.0,
       'Java, Spring Boot, Kotlin, PostgreSQL, Kafka, Kubernetes',
       'Eight years on JVM microservices at scale. Led a team of six on the marketplace search platform. Extensive Kafka and Kubernetes production experience, strong PostgreSQL. No professional Python.',
       'rejected', 'closed', 46, 30, 92, 80,
       'Excellent engineer with strong seniority, PostgreSQL and infrastructure experience, but the core stack is a mismatch — no professional Python or FastAPI. Rejected for this role; worth keeping in the talent pool.'),

      ('Hannah Weiss',     'hannah.weiss@example.com',     '+49 151 5550 288',
       'Berlin, Germany',    'Junior Backend Engineer', 'Delivery Hero',  2.0,
       'Python, Flask, PostgreSQL, Docker',
       'Two years post-graduation building internal Flask services. Strong fundamentals and fast learner, contributed to an internal API gateway. Has not yet owned a production service end to end.',
       'rejected', 'closed', 32, 45, 20, 68,
       'Well short of the 5+ year senior requirement and has not owned a production service. Good Python fundamentals — a reasonable candidate for a junior or mid-level opening, not this one.')
    ) as t(full_name, email, phone, location, current_title, current_company, years_exp,
           skills, profile_text, shortlist, stage, overall, skills_s, exp_s, edu_s, rationale)
  loop
    -- Talent pool entry (org-wide record, deduped on email)
    insert into public.talent_pool (
      organization_id, full_name, email, phone, location,
      current_title, current_company, years_experience, skills, profile_text, source
    )
    values (
      v_org, r.full_name, lower(r.email), r.phone, r.location,
      r.current_title, r.current_company, r.years_exp, r.skills, r.profile_text, 'csv_import'
    )
    on conflict (organization_id, email) where email is not null
    do update set full_name = excluded.full_name
    returning id into v_pool;

    -- Role-specific candidate record
    insert into public.candidates (
      organization_id, role_id, full_name, email, phone,
      resume_text, source, shortlist_status, stage, talent_pool_id
    )
    values (
      v_org, v_role, r.full_name, lower(r.email), r.phone,
      r.profile_text, 'csv_import', r.shortlist, r.stage, v_pool
    )
    returning id into v_cand;

    -- Score against the role
    insert into public.scores (
      organization_id, candidate_id, role_id,
      overall_score, skills_score, experience_score, education_score, rationale, model
    )
    values (
      v_org, v_cand, v_role,
      r.overall, r.skills_s, r.exp_s, r.edu_s, r.rationale, 'seed/manual'
    )
    on conflict (candidate_id, role_id) do nothing;
  end loop;

  raise notice 'Seeded 7 demo candidates into org % against role %.', v_org, v_role;
end $$;
