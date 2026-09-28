"""Application settings loaded from environment variables.

Dono: infra-docker. Consumido por todos os nós do orchestrator.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central settings object. All values come from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Database ---
    database_url: str = "postgresql+asyncpg://agent_portal:agent_portal@postgres:5432/agent_portal"

    # --- Auth / JWT ---
    jwt_secret: str = "change-me-in-prod"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # --- Worker ---
    worker_token: str = "change-me-in-prod"
    worker_url: str = "http://nginx:8081/execute"

    # --- MinIO / Garage (S3) ---
    # O client Python `minio` aceita APENAS ``host:port`` como endpoint
    # (schema ``http://``/``https://`` -> ValueError "path in endpoint is not
    # allowed"). As variaveis aceitam os dois formatos; ``minio_endpoint_host``
    # e ``minio_secure`` normalizam para o client. Dono: infra-docker.
    minio_root_user: str = "admin"
    minio_root_password: str = "change-me-in-prod"
    minio_endpoint: str = "minio:9001"
    minio_bucket_agents: str = "agents"
    minio_bucket_skills: str = "skills"
    minio_bucket_knowledge: str = "knowledge"

    # --- GitHub (integração, PAT com escopo repo:read) ---
    github_token: str = ""
    github_api_base: str = "https://api.github.com"

    # --- Integrações (criptografia dos tokens armazenados; Fernet) ---
    integrations_secret_key: str = ""

    # --- Admin (seed) ---
    admin_email: str = ""
    admin_password: str = ""
    admin_name: str = "Administrador"

    # --- LLM ---
    llm_provider: str = "mock"  # mock | openai
    openai_api_key: str = ""
    # Servidor compatível com OpenAI (vazio = api.openai.com). LLM_MODEL, se
    # definido, vale para o chat de construção e a execução de agentes.
    openai_base_url: str = ""
    llm_model: str = ""

    # --- Embeddings ---
    embedding_provider: str = "mock"  # mock | openai
    embedding_dim: int = 1536
    embedding_base_url: str = ""  # vazio = OPENAI_BASE_URL
    embedding_model: str = "text-embedding-3-small"
    # Prefixos de tarefa exigidos por alguns modelos (ex.: nomic-embed-text:
    # "search_query: " / "search_document: "). Vazio = texto puro.
    embedding_query_prefix: str = ""
    embedding_document_prefix: str = ""

    # --- CORS ---
    cors_origins: str = "http://localhost,http://localhost:80"

    # --- Email notifications (disabled by default) ---
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    enable_email_notifications: bool = False

    # --- Rivvn (gated by contract) ---
    rivvn_client_id: str = ""
    rivvn_client_secret: str = ""
    rivvn_base_url: str = "https://api.rivvn.ai"
    rivvn_redirect_uri: str = "http://localhost/api/integrations/rivvn/callback"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def minio_endpoint_host(self) -> str:
        """Endpoint para o client ``minio``: ``host:port`` (sem schema)."""
        value = self.minio_endpoint.strip()
        for prefix in ("https://", "http://"):
            if value.startswith(prefix):
                value = value[len(prefix):]
                break
        return value

    @property
    def minio_secure(self) -> bool:
        """True se o endpoint foi declarado com ``https://``."""
        return self.minio_endpoint.strip().startswith("https://")


@lru_cache
def get_settings() -> Settings:
    return Settings()


# Module-level singleton for convenience.
settings = get_settings()
