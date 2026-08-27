"""
Shared LLM configuration foundation for FinSentry AI.

Provides a unified configuration interface for all agent pipelines to query
model parameters, provider configurations, and timeout budgets without
making live network calls or coupling agents to specific SDKs.
"""

from typing import Dict, Optional

from pydantic import BaseModel, Field

from core.config import get_settings
from core.constants import LLMProvider


class LLMConfig(BaseModel):
    """Configuration structure for an LLM provider and model."""

    provider: LLMProvider
    model_name: str
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, gt=0)
    timeout_seconds: int = Field(default=60, gt=0)
    api_key_configured: bool = Field(default=False)


class LLMConfigService:
    """
    Service providing standard LLM configuration profiles across agents.
    """

    @staticmethod
    def get_default_config() -> LLMConfig:
        """Return the default LLM configuration configured in application settings."""
        settings = get_settings()
        provider_enum = LLMProvider(settings.DEFAULT_LLM_PROVIDER.lower())
        api_key = LLMConfigService.get_api_key_for_provider(provider_enum)

        return LLMConfig(
            provider=provider_enum,
            model_name=settings.DEFAULT_LLM_MODEL,
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=settings.LLM_MAX_TOKENS,
            timeout_seconds=settings.LLM_TIMEOUT_SECONDS,
            api_key_configured=bool(api_key),
        )

    @staticmethod
    def get_provider_config(
        provider: LLMProvider,
        model_name: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        timeout_seconds: Optional[int] = None,
    ) -> LLMConfig:
        """
        Build a customized configuration profile for a specific provider.
        """
        settings = get_settings()
        api_key = LLMConfigService.get_api_key_for_provider(provider)

                                                                      
        default_models: Dict[LLMProvider, str] = {
            LLMProvider.OLLAMA: getattr(settings, "OLLAMA_MODEL", "gpt-oss:120b-cloud"),
            LLMProvider.GOOGLE: "gemini-2.5-flash",
            LLMProvider.GROQ: "llama-3.3-70b-versatile",
            LLMProvider.OPENAI: "gpt-4o",
            LLMProvider.ANTHROPIC: "claude-3-5-sonnet-latest",
        }

        selected_model = model_name or default_models.get(provider, "default-model")
        selected_temp = temperature if temperature is not None else settings.LLM_TEMPERATURE
        selected_tokens = max_tokens if max_tokens is not None else settings.LLM_MAX_TOKENS
        selected_timeout = timeout_seconds if timeout_seconds is not None else settings.LLM_TIMEOUT_SECONDS

        return LLMConfig(
            provider=provider,
            model_name=selected_model,
            temperature=selected_temp,
            max_tokens=selected_tokens,
            timeout_seconds=selected_timeout,
            api_key_configured=bool(api_key),
        )

    @staticmethod
    def get_api_key_for_provider(provider: LLMProvider) -> str:
        """
        Retrieve the API key for the specified provider from application settings.
        """
        settings = get_settings()
        if provider == LLMProvider.OLLAMA:
            return getattr(settings, "OLLAMA_API_KEY", "")
        if provider == LLMProvider.GROQ:
            return settings.GROQ_API_KEY
        if provider == LLMProvider.GOOGLE:
            return settings.GOOGLE_API_KEY
        if provider == LLMProvider.OPENAI:
            return settings.OPENAI_API_KEY
        if provider == LLMProvider.ANTHROPIC:
            return settings.ANTHROPIC_API_KEY
        return ""


llm_config_service = LLMConfigService()
