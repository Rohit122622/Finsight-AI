"""
Application configuration loaded from environment variables.

Uses pydantic-settings for validation and type coercion.
The get_settings() function provides a cached singleton instance.
"""

from functools import lru_cache
from pathlib import Path
from typing import List

from dotenv import find_dotenv, load_dotenv
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

                                                               
_BACKEND_DIR = Path(__file__).resolve().parent.parent
_ENV_PATH = _BACKEND_DIR / ".env"

if _ENV_PATH.exists():
    load_dotenv(_ENV_PATH, override=True)
else:
    load_dotenv(find_dotenv(usecwd=True), override=True)


class Settings(BaseSettings):
    """
    Central application settings.

    All values are loaded from environment variables or a .env file
    located in the backend directory. Required variables without defaults
    will raise a validation error at startup if missing.
    """

    model_config = SettingsConfigDict(
        env_file=str(_ENV_PATH) if _ENV_PATH.exists() else ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

                                                                   
    APP_NAME: str = "FinSentry AI"
    APP_VERSION: str = "1.0.0"
    APP_ENV: str = "development"
    DEBUG: bool = False

                                                                   
    MONGODB_URI: str
    DATABASE_NAME: str = "finsentry"

                                                                   
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

                                                                   
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:5173/auth/google/callback"

                                                                   
    OLLAMA_ENABLED: bool = True
    OLLAMA_BASE_URL: str = "https://ollama.com"
    OLLAMA_API_KEY: str = ""
    OLLAMA_MODEL: str = "gpt-oss:120b-cloud"
    GROQ_API_KEY: str = ""
    GOOGLE_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""

                                                                   
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: str = ""
    REDIS_DB: int = 0
    REDIS_URL: str = ""
    CELERY_BROKER_URL: str = ""
    CELERY_RESULT_BACKEND: str = ""

                                                                   
    AGENT_DEFAULT_TIMEOUT_SECONDS: int = 300
    AGENT_MAX_RETRIES: int = 3
    AGENT_RETRY_BACKOFF_SECONDS: float = 2.0

                                                                   
    DEFAULT_LLM_PROVIDER: str = "ollama"
    DEFAULT_LLM_MODEL: str = "gpt-oss:120b-cloud"
    LLM_TIMEOUT_SECONDS: int = 60
    LLM_TEMPERATURE: float = 0.1
    LLM_MAX_TOKENS: int = 4096

                                         
    LLM_FALLBACK_ENABLED: bool = True
    LLM_PRIMARY_PROVIDER: str = "ollama"                           
    LLM_PRIMARY_MODEL: str = "gpt-oss:120b-cloud"
    LLM_OLLAMA_MODEL: str = "gpt-oss:120b-cloud"
    LLM_GOOGLE_MODEL: str = "gemini-2.5-flash"
    LLM_CLAUDE_MODEL: str = "claude-3-5-sonnet-latest"
    LLM_GROQ_MODEL: str = "llama-3.3-70b-versatile"
    LLM_MAX_RETRIES_PER_PROVIDER: int = 1
    LLM_RETRY_BACKOFF_SECONDS: float = 0.5
    LLM_PROVIDER_TIMEOUT_SECONDS: int = 30

                                                                   
    OBSERVABILITY_ENABLED: bool = True
    LANGSMITH_ENABLED: bool = False
    LANGSMITH_API_KEY: str = ""
    LANGSMITH_PROJECT: str = "finsentry-research-agent"
    LANGSMITH_ENDPOINT: str = "https://api.smith.langchain.com"
    PROMPT_LOGGING_ENABLED: bool = True
    TOKEN_TRACKING_ENABLED: bool = True

                                                                  
    STORAGE_DIR: str = "uploads"
    MAX_DOCUMENT_SIZE_BYTES: int = 25 * 1024 * 1024        
    MAX_DOCUMENT_PAGES: int = 100
    ALLOWED_DOCUMENT_EXTENSIONS: List[str] = [".pdf", ".txt", ".csv", ".md", ".json"]
    DEFAULT_CHUNK_SIZE: int = 1000
    DEFAULT_CHUNK_OVERLAP: int = 150

                                                                   
    R2_ACCOUNT_ID: str = ""
    R2_ACCESS_KEY_ID: str = ""
    R2_SECRET_ACCESS_KEY: str = ""
    R2_BUCKET_NAME: str = "finsentry-documents"
    R2_ENDPOINT_URL: str = ""
    R2_REGION: str = "auto"

                                                                   
    CLAMAV_HOST: str = "localhost"
    CLAMAV_PORT: int = 3310
    CLAMAV_ENABLED: bool = False
    SCANNER_FAIL_CLOSED: bool = True

                                                                   
    UPLOAD_RATE_LIMIT_REQUESTS: int = 10
    UPLOAD_RATE_LIMIT_WINDOW_SECONDS: int = 60

                                                                   
    FRONTEND_URL: str = "http://localhost:5173"
    CORS_ORIGINS: List[str] = []

    def get_redis_url(self) -> str:
        """Return the constructed or explicitly set Redis connection URL."""
        if self.REDIS_URL:
            return self.REDIS_URL
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"

    def get_celery_broker_url(self) -> str:
        """Return the Celery broker URL (defaults to get_redis_url())."""
        return self.CELERY_BROKER_URL or self.get_redis_url()

    def get_celery_result_backend(self) -> str:
        """Return the Celery result backend URL (defaults to get_redis_url())."""
        return self.CELERY_RESULT_BACKEND or self.get_redis_url()

    def get_r2_endpoint_url(self) -> str:
        """Return Cloudflare R2 endpoint URL constructed from account ID if not explicitly set."""
        if self.R2_ENDPOINT_URL:
            return self.R2_ENDPOINT_URL
        if self.R2_ACCOUNT_ID:
            return f"https://{self.R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
        return ""


    @field_validator("GOOGLE_REDIRECT_URI", mode="before")
    @classmethod
    def clean_redirect_uri(cls, v: str) -> str:
        """Strip whitespace and trim any trailing slashes from GOOGLE_REDIRECT_URI."""
        if isinstance(v, str):
            v = v.strip()
            if v.endswith("/"):
                v = v[:-1]
        return v

    @field_validator("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", mode="before")
    @classmethod
    def clean_google_credentials(cls, v: str) -> str:
        """Strip whitespace from Google Client ID and Secret."""
        if isinstance(v, str):
            return v.strip()
        return v

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: str | List[str], info) -> List[str]:
        """
        Accept a comma-separated string or a list.
        The frontend URL is always appended automatically in get_cors_origins().
        """
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    def get_cors_origins(self) -> List[str]:
        """Return the full list of allowed CORS origins, including FRONTEND_URL."""
        origins = list(self.CORS_ORIGINS)
        if self.FRONTEND_URL and self.FRONTEND_URL not in origins:
            origins.append(self.FRONTEND_URL)
        return origins

    def get_default_llm_config(self) -> "AgentLLMConfig":
        """Return unified default LLM configuration for agent tasks."""
        return AgentLLMConfig(
            provider=self.DEFAULT_LLM_PROVIDER,
            model_name=self.DEFAULT_LLM_MODEL,
            temperature=self.LLM_TEMPERATURE,
            max_tokens=self.LLM_MAX_TOKENS,
            timeout_seconds=self.LLM_TIMEOUT_SECONDS,
            api_key_configured=bool(
                self.GROQ_API_KEY or self.GOOGLE_API_KEY or self.OPENAI_API_KEY or self.ANTHROPIC_API_KEY
            ),
        )


class AgentLLMConfig(BaseSettings):
    """Configuration structure for shared agent LLM parameters."""

    provider: str = "groq"
    model_name: str = "llama-3.3-70b-versatile"
    temperature: float = 0.1
    max_tokens: int = 4096
    timeout_seconds: int = 60
    api_key_configured: bool = False


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Return a cached Settings singleton.

    The first call reads environment variables and validates them.
    Subsequent calls return the same instance without re-reading the env.
    """
    return Settings()
