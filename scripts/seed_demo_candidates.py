"""Seed 1 demo role + 7 dummy candidates for the signed-up owner's org.

Runs through the service key (bypasses RLS) so nothing has to be pasted into
the Supabase SQL editor. Idempotent: re-running updates rather than duplicates.

    cd backend && python ../scripts/seed_demo_candidates.py

Requires backend/.env to be configured and the schema to be applied.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.config import settings  # noqa: E402
from app.db import service_client  # noqa: E402

ROLE_TITLE = "Senior Backend Engineer"
ROLE_DESCRIPTION = (
    "We are hiring a senior backend engineer to own our Python/FastAPI services. "
    "Must have 5+ years building production APIs, strong PostgreSQL skills, and "
    "experience with async workloads, cloud deployment (AWS/GCP) and CI/CD. "
    "Nice to have: pgvector / retrieval systems, Kubernetes, and mentoring experience."
)

# Deliberately spread across score bands, shortlist statuses and stages so every
# filter in the UI has something to show.
CANDIDATES = [
    dict(
        full_name="Priya Raghavan", email="priya.raghavan@example.com",
        phone="+91 98200 41277", location="Bengaluru, India",
        current_title="Staff Backend Engineer", current_company="Flipkart",
        years_experience=9.0,
        skills="Python, FastAPI, PostgreSQL, Kafka, Kubernetes, AWS, pgvector",
        profile_text=(
            "Nine years building high-throughput commerce APIs. Led the migration of the "
            "order service to FastAPI and async SQLAlchemy, cutting p99 latency from 800ms "
            "to 120ms. Owns a pgvector-backed product search index serving 40M queries/day. "
            "Mentors five engineers."
        ),
        shortlist_status="approved", stage="interview",
        overall=92, skills_s=95, exp_s=94, edu_s=82,
        rationale=(
            "Exceptional match. Exceeds the 5-year bar, deep FastAPI + PostgreSQL ownership, "
            "and direct pgvector experience which is a listed nice-to-have. Mentoring is a bonus."
        ),
    ),
    dict(
        full_name="Daniel Okonkwo", email="daniel.okonkwo@example.com",
        phone="+44 7700 900431", location="Manchester, UK",
        current_title="Senior Software Engineer", current_company="Monzo",
        years_experience=7.0,
        skills="Python, Django, PostgreSQL, Terraform, GCP, Celery",
        profile_text=(
            "Seven years in fintech backends. Built the disputes platform handling 2M "
            "events/month on Django and Celery. Strong Postgres tuning background - rewrote "
            "the ledger query layer to cut read load by 60%. Terraform-managed GCP infra "
            "and full CI/CD ownership."
        ),
        shortlist_status="approved", stage="interview",
        overall=84, skills_s=82, exp_s=88, edu_s=80,
        rationale=(
            "Strong match on experience, PostgreSQL depth and cloud/CI-CD. Primary gap is "
            "FastAPI specifically - the async experience is Celery-based rather than ASGI, "
            "so some ramp-up expected."
        ),
    ),
    dict(
        full_name="Mei-Ling Chen", email="meiling.chen@example.com",
        phone="+1 415 555 0182", location="San Francisco, USA",
        current_title="Backend Engineer", current_company="Stripe",
        years_experience=6.0,
        skills="Go, Python, gRPC, PostgreSQL, Kubernetes, AWS",
        profile_text=(
            "Six years on payments infrastructure, primarily Go with Python tooling. "
            "Designed an idempotency layer processing $4B annually. Deep Kubernetes operator "
            "experience and on-call leadership for a tier-1 service."
        ),
        shortlist_status="approved", stage="outreach",
        overall=78, skills_s=72, exp_s=90, edu_s=78,
        rationale=(
            "Clears the experience bar comfortably and brings excellent distributed-systems "
            "and Kubernetes depth. Python is secondary to Go, so day-to-day FastAPI work "
            "would be a shift in primary language."
        ),
    ),
    dict(
        full_name="Arjun Mehta", email="arjun.mehta@example.com",
        phone="+91 99010 33845", location="Pune, India",
        current_title="Backend Developer", current_company="Zoho",
        years_experience=5.0,
        skills="Python, FastAPI, MySQL, Redis, Docker, REST",
        profile_text=(
            "Five years building internal SaaS APIs. Migrated three services from Flask to "
            "FastAPI and introduced async request handling. Comfortable with Docker-based "
            "deploys, though infrastructure is largely managed by a separate platform team."
        ),
        shortlist_status="pending", stage="screening",
        overall=71, skills_s=78, exp_s=66, edu_s=72,
        rationale=(
            "Meets the minimum 5-year requirement with directly relevant FastAPI migration "
            "work. Weaker on PostgreSQL (MySQL background) and has limited hands-on "
            "cloud/CI-CD ownership."
        ),
    ),
    dict(
        full_name="Sofia Almeida", email="sofia.almeida@example.com",
        phone="+351 912 555 704", location="Lisbon, Portugal",
        current_title="Full Stack Engineer", current_company="Remote.com",
        years_experience=4.5,
        skills="TypeScript, Node.js, Python, PostgreSQL, React, AWS",
        profile_text=(
            "Four and a half years split across frontend and backend. Owns the billing "
            "integration service in Node with a Python reporting pipeline. Solid PostgreSQL "
            "schema design and AWS Lambda deployment experience."
        ),
        shortlist_status="pending", stage="screening",
        overall=58, skills_s=55, exp_s=52, edu_s=74,
        rationale=(
            "Slightly under the 5-year bar and the experience is split across the stack "
            "rather than backend-focused. Good PostgreSQL and AWS signal, but Python is "
            "not the primary language."
        ),
    ),
    dict(
        full_name="Tomasz Wojcik", email="tomasz.wojcik@example.com",
        phone="+48 512 555 913", location="Krakow, Poland",
        current_title="Java Backend Engineer", current_company="Allegro",
        years_experience=8.0,
        skills="Java, Spring Boot, Kotlin, PostgreSQL, Kafka, Kubernetes",
        profile_text=(
            "Eight years on JVM microservices at scale. Led a team of six on the marketplace "
            "search platform. Extensive Kafka and Kubernetes production experience, strong "
            "PostgreSQL. No professional Python."
        ),
        shortlist_status="rejected", stage="closed",
        overall=46, skills_s=30, exp_s=92, edu_s=80,
        rationale=(
            "Excellent engineer with strong seniority, PostgreSQL and infrastructure "
            "experience, but the core stack is a mismatch - no professional Python or "
            "FastAPI. Rejected for this role; worth keeping in the talent pool."
        ),
    ),
    dict(
        full_name="Hannah Weiss", email="hannah.weiss@example.com",
        phone="+49 151 5550 288", location="Berlin, Germany",
        current_title="Junior Backend Engineer", current_company="Delivery Hero",
        years_experience=2.0,
        skills="Python, Flask, PostgreSQL, Docker",
        profile_text=(
            "Two years post-graduation building internal Flask services. Strong fundamentals "
            "and fast learner, contributed to an internal API gateway. Has not yet owned a "
            "production service end to end."
        ),
        shortlist_status="rejected", stage="closed",
        overall=32, skills_s=45, exp_s=20, edu_s=68,
        rationale=(
            "Well short of the 5+ year senior requirement and has not owned a production "
            "service. Good Python fundamentals - a reasonable candidate for a junior or "
            "mid-level opening, not this one."
        ),
    ),
]


def main() -> int:
    db = service_client()

    members = db.table("organization_members").select(
        "organization_id, user_id, member_role, created_at"
    ).order("created_at").limit(1).execute().data

    if not members:
        print(
            "No organization found.\n"
            "Sign up in the app first (http://localhost:5173/signup) - signup is what\n"
            "creates the organization this seed attaches to."
        )
        return 1

    org_id = members[0]["organization_id"]
    user_id = members[0]["user_id"]
    org = db.table("organizations").select("name").eq("id", org_id).single().execute().data
    print(f"Seeding into org '{org['name']}' ({org_id})")

    existing = db.table("roles").select("id").eq("organization_id", org_id).eq(
        "title", ROLE_TITLE
    ).limit(1).execute().data

    if existing:
        role_id = existing[0]["id"]
        print(f"  role: reusing existing '{ROLE_TITLE}'")
    else:
        role_id = db.table("roles").insert({
            "organization_id": org_id,
            "title": ROLE_TITLE,
            "description": ROLE_DESCRIPTION,
            "status": "open",
            "created_by": user_id,
        }).execute().data[0]["id"]
        print(f"  role: created '{ROLE_TITLE}'")

    for c in CANDIDATES:
        email = c["email"].lower()

        # talent_pool's unique index is partial (`where email is not null`), which
        # ON CONFLICT cannot infer — so match explicitly rather than upsert.
        pool_payload = {
            "organization_id": org_id,
            "full_name": c["full_name"],
            "email": email,
            "phone": c["phone"],
            "location": c["location"],
            "current_title": c["current_title"],
            "current_company": c["current_company"],
            "years_experience": c["years_experience"],
            "skills": c["skills"],
            "profile_text": c["profile_text"],
            "source": "csv_import",
        }
        prior_pool = db.table("talent_pool").select("id").eq(
            "organization_id", org_id
        ).eq("email", email).limit(1).execute().data

        if prior_pool:
            pool = db.table("talent_pool").update(pool_payload).eq(
                "id", prior_pool[0]["id"]
            ).execute().data[0]
        else:
            pool = db.table("talent_pool").insert(pool_payload).execute().data[0]

        prior = db.table("candidates").select("id").eq(
            "organization_id", org_id
        ).eq("role_id", role_id).eq("email", email).limit(1).execute().data

        payload = {
            "organization_id": org_id,
            "role_id": role_id,
            "full_name": c["full_name"],
            "email": email,
            "phone": c["phone"],
            "resume_text": c["profile_text"],
            "source": "csv_import",
            "shortlist_status": c["shortlist_status"],
            "stage": c["stage"],
            "talent_pool_id": pool["id"],
        }

        if prior:
            cand_id = prior[0]["id"]
            db.table("candidates").update(payload).eq("id", cand_id).execute()
        else:
            cand_id = db.table("candidates").insert(payload).execute().data[0]["id"]

        db.table("scores").upsert({
            "organization_id": org_id,
            "candidate_id": cand_id,
            "role_id": role_id,
            "overall_score": c["overall"],
            "skills_score": c["skills_s"],
            "experience_score": c["exp_s"],
            "education_score": c["edu_s"],
            "rationale": c["rationale"],
            "model": "seed/manual",
        }, on_conflict="candidate_id,role_id").execute()

        print(f"  candidate: {c['full_name']:<18} score {c['overall']:>3}  {c['shortlist_status']}/{c['stage']}")

    print(f"\nDone - 7 candidates seeded against '{ROLE_TITLE}'.")
    print(f"Supabase: {settings.supabase_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
