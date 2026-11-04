from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    supabase_url: str
    supabase_secret_key: str
    # --- NVIDIA NIM (current provider) -------------------------------------
    # NIM speaks the OpenAI chat-completions API, so the client is the `openai`
    # SDK pointed at NVIDIA's base URL rather than a bespoke one.
    nvidia_api_key: str = ""
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    # The model must honour OpenAI-style response_format json_schema and return
    # its answer in `content`, which every call in this codebase relies on.
    # nemotron-3.5-bolt-e4b does both, ~2s (measured 2026-11-04). On the free
    # endpoints gpt-oss-120b now returns 410 Gone and gpt-oss-20b accepts the
    # request and never answers.
    #
    # nvidia_model is the DEFAULT and is fast, because most calls are either
    # interactive (a recruiter waiting on an email draft or the next interview
    # question) or high-volume (one call per batch of 8 candidates scored).
    #
    # nvidia_quality_model is opted into per call site by passing quality=True to
    # _generate_json. It is reserved for output that is written once, read
    # carefully by a human, and expensive to get wrong — currently the LinkedIn
    # post and the interview transcript scoring. Do not make it the default:
    # at ~101s a call it would put minutes into every screen in the app.
    nvidia_model: str = "nvidia/nemotron-3.5-bolt-e4b"
    nvidia_quality_model: str = "nvidia/nemotron-3.5-bolt-e4b"
    nvidia_fallback_model: str = "nvidia/nemotron-3.5-bolt-e4b"
    # Seconds before a stalled NVIDIA call is abandoned for the backup provider.
    nvidia_timeout_seconds: float = 45.0
    # Natively 2048-dimensional; requested at 1024 because
    # ai_embeddings.embedding is vector(1024) (0011).
    nvidia_embedding_model: str = "nvidia/nemotron-3.5-embed-1b"
    nvidia_embedding_dim: int = 1024

    # --- Backup provider for the platform key --------------------------------
    # Any OpenAI-compatible endpoint. When the NVIDIA call fails after its own
    # retries (rate limit, outage, rejected key, no credit) the same prompt is
    # sent here instead, and if NVIDIA_API_KEY is empty this becomes the
    # primary. Defaults to Groq's free tier serving the same gpt-oss-20b, so the
    # prompts and JSON schemas behave identically on either side.
    #
    # Chat only: Groq has no embeddings endpoint, so semantic search still
    # needs NVIDIA. Organizations with their own provider never fail over here;
    # that would spend the platform's quota on their behalf.
    backup_ai_api_key: str = ""
    backup_ai_base_url: str = "https://api.groq.com/openai/v1"
    backup_ai_model: str = "openai/gpt-oss-20b"

    # --- Gemini (retired) ---------------------------------------------------
    # Kept so existing .env files and the Render blueprint do not fail to parse.
    # Nothing reads these any more.
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_fallback_model: str = "gemini-2.5-flash-lite"
    # text-embedding-004 was retired from the v1beta API (404 on embedContent).
    # gemini-embedding-001 replaces it and is Matryoshka-trained, so asking for
    # 768 dimensions keeps ai_embeddings.embedding as vector(768) unchanged.
    # Vectors below 3072 dimensions come back UNNORMALISED, which is exactly
    # why the HNSW index uses vector_cosine_ops rather than L2.
    gemini_embedding_model: str = "gemini-embedding-001"
    gemini_embedding_dim: int = 768
    resend_api_key: str = ""
    # Until a domain is verified in Resend, only onboarding@resend.dev works
    # as sender and delivery is restricted to the Resend account owner's email.
    email_from: str = "Recruit AI <onboarding@resend.dev>"
    # Sending from resend.dev silently reaches nobody except the Resend account
    # owner: Resend accepts the call and returns an id, the outbox row goes
    # green, and the candidate never hears from you. That is the worst possible
    # failure for an outreach product, so it is refused unless someone opts in
    # on purpose. Set true for local development; never set it in production.
    allow_sandbox_email: bool = False
    # Whether a new account must click a link in its inbox before it works.
    #
    # Defaults to FALSE, and that default is load-bearing: turning this on while
    # outbound mail cannot actually reach strangers would mean nobody can ever
    # finish signing up. Enable it only once EMAIL_FROM is a verified domain —
    # the same switch that makes candidate outreach work.
    #
    # Until then anyone can register with an address they do not own, which is
    # fine for a demo and wrong for a public product. See signup.py.
    require_email_verification: bool = False
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/calendar/oauth/callback"
    frontend_url: str = "http://localhost:5173"
    scheduler_timezone: str = "Asia/Kolkata"
    scheduler_interval_seconds: int = 900
    cors_origins: str = "http://localhost:5173"
    # --- Bring-your-own AI provider (see services/ai_provider.py) ----------
    # Fernet key that encrypts each organization's provider API key at rest.
    # Generate with:  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # Losing or changing it makes every stored key unreadable (owners re-enter
    # them); leaking it together with a database dump leaks every key.
    ai_keys_encryption_key: str = ""
    # Workspaces without their own key run on the platform key (NVIDIA_*
    # above) for this many model calls per calendar month (UTC), then are
    # asked to add their own. 0 = no free allowance at all.
    platform_ai_monthly_limit: int = 100
    # --- Platform admin (routers/admin.py) --------------------------------
    # Comma-separated auth user IDs allowed into /admin. IDs, not emails:
    # while email verification is off anyone can register any address, but
    # nobody can choose an existing account's id.
    platform_admin_user_ids: str = ""
    # Detailed activity rows older than this are folded into permanent daily
    # totals and deleted. State this period in the privacy notice.
    activity_retention_days: int = 365
    # Shown on the public privacy page. Empty = point people at @tryrecruitai.
    privacy_contact_email: str = ""
    # Serve /docs, /redoc and /openapi.json. Leave false anywhere reachable
    # from the internet: they are a complete map of the API for an attacker.
    expose_api_docs: bool = False

    @property
    def admin_ids(self) -> set[str]:
        return {i.strip() for i in self.platform_admin_user_ids.split(",") if i.strip()}

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
