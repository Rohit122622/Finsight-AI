"""
FinSentry AI — Phase 3D Prompt Engineering Contracts.

Strongly typed Pydantic schemas for the Prompt Engineering layer:
  - Prompt versions and configurations
  - Modular prompt sections (system, research, citation, format, refusal)
  - Composed PromptPackage envelope with section breakdowns and token estimates
  - PromptBuildRequest for internal and diagnostic usage
"""

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from schemas.context import ContextLimitsConfig, ResearchContext
from schemas.query_understanding import QueryUnderstandingResult


class PromptVersion(str, Enum):
    """Supported prompt template versions for reproducibility & evaluation."""

    V1 = "v1.0.0"
    V1_STRICT = "v1.0.0-strict"
    V1_FAST = "v1.0.0-fast"


class ResponseStyle(str, Enum):
    """Desired style and tone for financial research answers."""

    PROFESSIONAL_ANALYTIC = "PROFESSIONAL_ANALYTIC"
    EXECUTIVE_SUMMARY = "EXECUTIVE_SUMMARY"
    DETAILED_AUDIT = "DETAILED_AUDIT"


class CitationMode(str, Enum):
    """Citation requirement mode."""

    STRICT = "STRICT"
    STANDARD = "STANDARD"


class RefusalMode(str, Enum):
    """Refusal strictness when context is lacking."""

    STRICT_REFUSAL = "STRICT_REFUSAL"
    PARTIAL_WITH_LIMITATIONS = "PARTIAL_WITH_LIMITATIONS"


class PromptConfiguration(BaseModel):
    """Runtime configuration for modular prompt generation."""

    version: PromptVersion = Field(default=PromptVersion.V1, description="Prompt version identifier")
    response_style: ResponseStyle = Field(
        default=ResponseStyle.PROFESSIONAL_ANALYTIC,
        description="Desired analytical response tone",
    )
    citation_mode: CitationMode = Field(
        default=CitationMode.STRICT,
        description="Citation strictness (STRICT requires exact chunk citations)",
    )
    strict_evidence_mode: bool = Field(
        default=True,
        description="Whether to prohibit any external speculation beyond supplied evidence",
    )
    refusal_mode: RefusalMode = Field(
        default=RefusalMode.STRICT_REFUSAL,
        description="Refusal behavior on insufficient evidence",
    )
    include_delimiters: bool = Field(
        default=True,
        description="Wrap evidence in XML-style delimiters for injection safety",
    )


class PromptSection(BaseModel):
    """An individual modular prompt component."""

    name: str = Field(..., description="Section identifier (e.g. system, research, citation)")
    version: str = Field(..., description="Component version string")
    content: str = Field(..., description="Text content of the prompt section")
    character_count: int = Field(default=0, description="Character count")
    token_estimate: int = Field(default=0, description="Estimated token count")


class PromptMetadata(BaseModel):
    """Metadata regarding prompt composition and token sizing."""

    version: str = Field(..., description="Overall prompt package version")
    total_characters: int = Field(default=0, description="Sum of all section characters")
    total_token_estimate: int = Field(default=0, description="Sum of estimated tokens")
    section_breakdown: Dict[str, int] = Field(
        default_factory=dict, description="Token estimates by section name"
    )
    has_source_evidence: bool = Field(default=False)
    has_conversation_context: bool = Field(default=False)
    has_session_memory: bool = Field(default=False)
    has_query_understanding: bool = Field(default=False)
    evidence_chunks_count: int = Field(default=0)
    metrics_count: int = Field(default=0)
    red_flags_count: int = Field(default=0)
    comparisons_count: int = Field(default=0)
    history_messages_count: int = Field(default=0)


class PromptPackage(BaseModel):
    """
    Complete modular prompt package ready for LLM invocation (Phase 3E).
    Does NOT invoke the LLM or generate the financial answer.
    """

    session_id: str = Field(..., description="Owning research session ID")
    user_id: str = Field(..., description="Owning user ID")
    system_prompt: str = Field(..., description="Complete reusable system instructions")
    research_prompt: str = Field(..., description="Structured task and context payload")
    citation_prompt: str = Field(..., description="Citation rules and instructions")
    response_format_prompt: str = Field(..., description="Output JSON schema instructions")
    refusal_prompt: str = Field(..., description="Strict refusal and limitation instructions")
    composed_user_prompt: str = Field(
        ..., description="Fully assembled user turn containing task, context, citation, format, refusal"
    )
    sections: List[PromptSection] = Field(default_factory=list, description="Individual modular sections")
    config: PromptConfiguration = Field(..., description="Configuration used to build this prompt")
    metadata: PromptMetadata = Field(..., description="Operational sizing and breakdown metadata")


class PromptBuildRequest(BaseModel):
    """Request payload for internal and diagnostic prompt building."""

    query: str = Field(..., min_length=1, description="User research question")
    query_understanding: Optional[QueryUnderstandingResult] = Field(
        default=None, description="Pre-computed Phase 3B understanding"
    )
    context: Optional[ResearchContext] = Field(
        default=None, description="Pre-built Phase 3C research context"
    )
    config: Optional[PromptConfiguration] = Field(
        default=None, description="Custom prompt configuration"
    )
    limits: Optional[ContextLimitsConfig] = Field(
        default=None, description="Context limits if auto-building context"
    )
    auto_build_context: bool = Field(
        default=True,
        description="Whether to automatically build context if context is None",
    )
