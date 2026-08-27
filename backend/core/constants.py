"""
Core constants and enums for FinSentry AI.
"""

from enum import Enum


class JobStatus(str, Enum):
    """Lifecycle states of asynchronous agent tasks."""

    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    EXTRACTING = "EXTRACTING"
    EMBEDDING = "EMBEDDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class DocumentStatus(str, Enum):
    """Lifecycle states of an ingested document."""

    UPLOADED = "UPLOADED"
    PROCESSING = "PROCESSING"
    PROCESSED = "PROCESSED"
    INDEXED = "INDEXED"
    FAILED = "FAILED"


class AgentTaskType(str, Enum):
    """Categorization of agent tasks across all phases."""

    DUMMY_TASK = "DUMMY_TASK"
    DOCUMENT_ANALYSIS = "DOCUMENT_ANALYSIS"
    DOCUMENT_PROCESSING = "DOCUMENT_PROCESSING"
    EXTRACTION = "EXTRACTION"
    RED_FLAG_ANALYSIS = "RED_FLAG_ANALYSIS"
    COMPARISON = "COMPARISON"
    RESEARCH = "RESEARCH"
    REPORT_GENERATION = "REPORT_GENERATION"


class LLMProvider(str, Enum):
    """Supported LLM providers for shared configuration."""

    OLLAMA = "ollama"
    GROQ = "groq"
    GOOGLE = "google"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


class DummyAgentMode(str, Enum):
    """Deterministic modes for the Phase 2A DummyAgent."""

    SUCCESS = "SUCCESS"
    TRANSIENT_FAILURE = "TRANSIENT_FAILURE"
    PERMANENT_FAILURE = "PERMANENT_FAILURE"
    TIMEOUT = "TIMEOUT"
