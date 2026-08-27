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
    # gpt-oss-* honour OpenAI-style response_format json_schema, which is what
    # every call in this codebase relies on. The nemotron reasoning models
    # return their text in `reasoning_content` and leave `content` null, so they
    # are NOT drop-in replacements here.
    #
    # Two tiers, chosen on measured latency (2026-08-10, 40-token reply on this
    # account): gpt-oss-20b ~1.2s, gpt-oss-120b ~82.7s, glm-5.2 ~101s.
    #
    # nvidia_model is the DEFAULT and is fast, because most calls are either
    # interactive (a recruiter waiting on an email draft or the next interview
    # question) or high-volume (one call per batch of 8 candidates scored).
    #
    # nvidia_quality_model is opted into per call site by passing model= to
    # _generate_json. It is reserved for output that is written once, read
    # carefully by a human, and expensive to get wrong — currently the LinkedIn
    # post and the interview transcript scoring. Do not make it the default:
    # at ~101s a call it would put minutes into every screen in the app.
    nvidia_model: str = "openai/gpt-oss-20b"
    nvidia_quality_model: str = "z-ai/glm-5.2"
    nvidia_fallback_model: str = "openai/gpt-oss-20b"
    # 1024-dimensional; ai_embeddings.embedding is vector(1024) to match (0011).
    nvidia_embedding_model: str = "nvidia/nv-embedqa-e5-v5"
    nvidia_embedding_dim: int = 1024

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
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/api/calendar/oauth/callback"
    frontend_url: str = "http://localhost:5173"
    scheduler_timezone: str = "Asia/Kolkata"
    scheduler_interval_seconds: int = 900
    cors_origins: str = "http://localhost:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
