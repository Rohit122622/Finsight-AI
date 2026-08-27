"""
Pydantic contracts and schemas for Phase 3F — LLM Fallback Chain.
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from core.constants import LLMProvider


class LLMErrorCategory(str, Enum):
    """Categorization of LLM invocation errors."""

    TRANSIENT_NETWORK = "TRANSIENT_NETWORK"
    TIMEOUT = "TIMEOUT"
    RATE_LIMIT = "RATE_LIMIT"
    SERVER_ERROR = "SERVER_ERROR"
    AUTH_ERROR = "AUTH_ERROR"
    INVALID_REQUEST = "INVALID_REQUEST"
    MALFORMED_RESPONSE = "MALFORMED_RESPONSE"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"
    EXHAUSTED = "EXHAUSTED"


class ProviderInvocationMetadata(BaseModel):
    """Execution telemetry and tracking for a single LLM provider attempt."""

    provider: LLMProvider
    model: str
    latency_ms: float = Field(default=0.0, description="Latency in milliseconds")
    success: bool = Field(default=False)
    failure_reason: Optional[str] = Field(default=None)
    error_category: Optional[LLMErrorCategory] = Field(default=None)
    is_transient: bool = Field(default=False)
    fallback_attempt: int = Field(default=1, description="1-indexed sequence in fallback chain")
    retry_attempt: int = Field(default=0, description="0-indexed retry count for this specific provider")
    prompt_tokens_est: Optional[int] = Field(default=None)
    completion_tokens_est: Optional[int] = Field(default=None)
    total_tokens_est: Optional[int] = Field(default=None)


class LLMFallbackResult(BaseModel):
    """Unified result of LLM inference through the fallback chain."""

    content: str = Field(default="", description="Generated response text")
    structured_json: Optional[Dict[str, Any]] = Field(default=None)
    primary_provider: LLMProvider
    selected_provider: LLMProvider
    selected_model: str
    is_fallback: bool = Field(default=False)
    fallback_attempts_count: int = Field(default=1)
    invocations_log: List[ProviderInvocationMetadata] = Field(default_factory=list)
    execution_time_ms: float = Field(default=0.0)
    status: str = Field(default="completed")
    error_message: Optional[str] = Field(default=None)


class LLMFallbackChainConfig(BaseModel):
    """Configuration contract for LLM fallback chain execution."""

    enabled: bool = Field(default=True)
    primary_provider: Optional[LLMProvider] = Field(default=None)
    primary_model: Optional[str] = Field(default=None)
    ollama_model: str = Field(default="gpt-oss:120b-cloud")
    google_model: str = Field(default="gemini-2.5-flash")
    claude_model: str = Field(default="claude-3-5-sonnet-latest")
    groq_model: str = Field(default="qwen/qwen3.6-27b")
    max_retries_per_provider: int = Field(default=1, ge=0, le=5)
    retry_backoff_seconds: float = Field(default=0.5, ge=0.0)
    timeout_seconds: int = Field(default=30, gt=0)
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    max_tokens: int = Field(default=4096, gt=0)
