"""Bring-your-own AI provider + free-allowance verification.

Prereqs: migration 0013 applied, backend on 127.0.0.1:8000 started with
PLATFORM_AI_MONTHLY_LIMIT=3, NVIDIA_API_KEY set. GEMINI_API_KEY in
backend/.env is optional (enables the second-provider check).

Run:  python scripts/verify_ai_provider.py
"""
import os
import sys
import uuid

import httpx
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "backend", ".env"))
SUPABASE_URL = os.environ["SUPABASE_URL"]
SECRET_KEY = os.environ["SUPABASE_SECRET_KEY"]
NVIDIA_KEY = os.environ.get("NVIDIA_API_KEY", "")
GEMINI_KEY = os.environ.get("VERIFY_SECOND_PROVIDER_KEY", "")  # optional: a live Gemini key
API = os.environ.get("API", "http://127.0.0.1:8000")
admin = {"apikey": SECRET_KEY, "Authorization": f"Bearer {SECRET_KEY}"}
failures = []


def check(name, ok, detail=""):
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail and not ok else ""))
    if not ok:
        failures.append(name)


def make_user(org_name=None):
    email = f"verifyai-{uuid.uuid4().hex[:8]}@example.com"
    pw = "Verify-" + uuid.uuid4().hex[:12]
    httpx.post(f"{SUPABASE_URL}/auth/v1/admin/users", headers=admin,
               json={"email": email, "password": pw, "email_confirm": True}, timeout=15).raise_for_status()
    tok = httpx.post(f"{SUPABASE_URL}/auth/v1/token?grant_type=password", headers={"apikey": SECRET_KEY},
                     json={"email": email, "password": pw}, timeout=15).json()["access_token"]
    H = {"Authorization": f"Bearer {tok}"}
    if org_name:
        httpx.post(f"{API}/api/organizations/bootstrap", headers=H,
                   json={"organization_name": org_name}, timeout=20).raise_for_status()
    return email, H


def main():
    owner_email, H = make_user("AI Provider Verify Org")
    org_id = httpx.get(f"{API}/api/organizations/me", headers=H, timeout=20).json()["id"]
    role = httpx.post(f"{API}/api/roles", headers=H, json={
        "title": "Data Analyst", "description": "SQL, Python, dashboards. 2+ years in analytics."}, timeout=20).json()

    print("Free allowance (limit 3 for this test):")
    st = httpx.get(f"{API}/api/ai-provider", headers=H, timeout=20).json()
    check("starts on free allowance with 0 used",
          st["usage"]["using_free_allowance"] and st["usage"]["used"] == 0 and st["usage"]["limit"] == 3, str(st["usage"]))
    check("owner can edit", st["can_edit"] is True)
    codes = [httpx.post(f"{API}/api/roles/{role['id']}/boolean-search", headers=H, timeout=300).status_code
             for _ in range(4)]
    check("first 3 AI calls allowed", codes[:3] == [200, 200, 200], str(codes))
    r = httpx.post(f"{API}/api/roles/{role['id']}/boolean-search", headers=H, timeout=300)
    check("call over the limit refused with 402", codes[3] == 402 and r.status_code == 402, f"{codes} {r.status_code}")
    check("refusal tells them to add their own key", "Settings → AI provider" in r.json().get("detail", ""), r.text[:200])
    st = httpx.get(f"{API}/api/ai-provider", headers=H, timeout=20).json()
    check("usage counter recorded the calls", st["usage"]["used"] >= 4, str(st["usage"]))

    print("\nCandidate-facing calls are never cut off:")
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
    from app.services import ai_provider as ap
    try:
        ap.meter_platform_call(org_id, candidate_facing=True)
        check("candidate-facing call passes over the limit", True)
    except Exception as e:  # noqa: BLE001
        check("candidate-facing call passes over the limit", False, repr(e))

    print("\nValidation and SSRF:")
    for base in ("http://api.example.com/v1", "https://127.0.0.1:54421/v1", "https://localhost/v1",
                 "https://169.254.169.254/v1"):
        r = httpx.put(f"{API}/api/ai-provider", headers=H, json={
            "provider": "custom", "base_url": base, "api_key": "sk-test", "model": "x"}, timeout=60)
        check(f"custom URL refused: {base}", r.status_code == 400, f"{r.status_code} {r.text[:120]}")
    r = httpx.put(f"{API}/api/ai-provider", headers=H, json={
        "provider": "nvidia", "api_key": "nvapi-definitely-not-valid", "model": "openai/gpt-oss-20b"}, timeout=120)
    check("bad key refused and explained", r.status_code == 400 and "rejected" in r.text, f"{r.status_code} {r.text[:200]}")
    st = httpx.get(f"{API}/api/ai-provider", headers=H, timeout=20).json()
    check("a failed test saves nothing", st["config"] is None)
    r = httpx.put(f"{API}/api/ai-provider", headers=H, json={
        "provider": "nvidia", "model": "openai/gpt-oss-20b"}, timeout=60)
    check("no key and nothing saved -> asks for key", r.status_code == 400, f"{r.status_code}")

    print("\nOwn provider (NVIDIA key entered as the workspace's own):")
    r = httpx.post(f"{API}/api/ai-provider/models", headers=H,
                   json={"provider": "nvidia", "api_key": NVIDIA_KEY}, timeout=60)
    check("model list loads", r.status_code == 200 and "openai/gpt-oss-20b" in r.json().get("models", []),
          f"{r.status_code} {r.text[:150]}")
    r = httpx.put(f"{API}/api/ai-provider", headers=H, json={
        "provider": "nvidia", "api_key": NVIDIA_KEY, "model": "openai/gpt-oss-20b"}, timeout=300)
    check("valid key tested and saved", r.status_code == 200 and r.json()["config"]["provider"] == "nvidia",
          f"{r.status_code} {r.text[:200]}")
    body = r.text
    check("API key never returned", NVIDIA_KEY not in body and r.json()["config"]["key_last4"] == NVIDIA_KEY[-4:])
    row = httpx.get(f"{SUPABASE_URL}/rest/v1/org_ai_providers?organization_id=eq.{org_id}&select=api_key_ciphertext",
                    headers=admin, timeout=20).json()[0]
    check("key stored encrypted", NVIDIA_KEY not in row["api_key_ciphertext"] and row["api_key_ciphertext"].startswith("gAAAA"))
    r = httpx.post(f"{API}/api/roles/{role['id']}/boolean-search", headers=H, timeout=300)
    check("AI works again past the free limit on own key", r.status_code == 200, f"{r.status_code} {r.text[:200]}")
    used_before = httpx.get(f"{API}/api/ai-provider", headers=H, timeout=20).json()["usage"]["used"]
    httpx.post(f"{API}/api/roles/{role['id']}/boolean-search", headers=H, timeout=300)
    used_after = httpx.get(f"{API}/api/ai-provider", headers=H, timeout=20).json()["usage"]["used"]
    check("own-key calls do not use the free allowance", used_after == used_before, f"{used_before}->{used_after}")
    r = httpx.put(f"{API}/api/ai-provider", headers=H, json={
        "provider": "custom", "base_url": "https://api.example.com/v1", "model": "x"}, timeout=60)
    check("saved key is not sent to a different endpoint", r.status_code == 400, f"{r.status_code} {r.text[:150]}")

    if GEMINI_KEY:
        print("\nSecond provider (Google Gemini via its OpenAI-compatible API):")
        r = httpx.post(f"{API}/api/ai-provider/models", headers=H,
                       json={"provider": "gemini", "api_key": GEMINI_KEY}, timeout=60)
        models = r.json().get("models", []) if r.status_code == 200 else []
        check("gemini model list loads", r.status_code == 200 and models, f"{r.status_code} {r.text[:200]}")
        pick = next((m for m in models if "flash" in m and "lite" not in m and "image" not in m
                     and "tts" not in m and "live" not in m and "audio" not in m), None)
        if pick:
            r = httpx.put(f"{API}/api/ai-provider", headers=H, json={
                "provider": "gemini", "api_key": GEMINI_KEY, "model": pick.removeprefix("models/")}, timeout=300)
            check(f"gemini {pick} tested and saved", r.status_code == 200, f"{r.status_code} {r.text[:250]}")
            if r.status_code == 200:
                r = httpx.post(f"{API}/api/roles/{role['id']}/boolean-search", headers=H, timeout=300)
                check("real feature runs on gemini", r.status_code == 200 and "linkedin" in r.text.lower(),
                      f"{r.status_code} {r.text[:250]}")

    print("\nPermissions:")
    _, H2 = make_user()
    httpx.post(f"{SUPABASE_URL}/rest/v1/organization_members", headers=admin, json={
        "organization_id": org_id,
        "user_id": httpx.get(f"{SUPABASE_URL}/auth/v1/user", headers={"apikey": SECRET_KEY, **H2}, timeout=15).json()["id"],
        "member_role": "recruiter"}, timeout=20).raise_for_status()
    st = httpx.get(f"{API}/api/ai-provider", headers=H2, timeout=20).json()
    check("recruiter sees provider but cannot edit", st["can_edit"] is False and st["config"] is not None)
    check("recruiter never sees key digits or URL", "key_last4" not in st["config"] and "base_url" not in st["config"])
    r = httpx.delete(f"{API}/api/ai-provider", headers=H2, timeout=20)
    check("recruiter cannot remove provider", r.status_code == 403, f"{r.status_code}")
    r = httpx.delete(f"{API}/api/ai-provider", headers=H, timeout=20)
    check("owner can remove provider (back to free allowance)",
          r.status_code == 200 and r.json()["config"] is None, f"{r.status_code}")

    print("\nCleanup...")
    httpx.delete(f"{SUPABASE_URL}/rest/v1/organizations?id=eq.{org_id}", headers=admin, timeout=20)
    users = httpx.get(f"{SUPABASE_URL}/auth/v1/admin/users?per_page=200", headers=admin, timeout=20).json()["users"]
    for u in users:
        if (u.get("email") or "").startswith("verifyai-"):
            httpx.delete(f"{SUPABASE_URL}/auth/v1/admin/users/{u['id']}", headers=admin, timeout=20)

    print()
    if failures:
        print(f"{len(failures)} check(s) FAILED")
        sys.exit(1)
    print("All AI provider checks passed.")


if __name__ == "__main__":
    main()
