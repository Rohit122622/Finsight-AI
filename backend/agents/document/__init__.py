"""
Document processing agents for FinSentry AI.
"""

from typing import Any


def __getattr__(name: str) -> Any:
    if name in (
        "DocumentAgent",
        "document_agent",
        "DocumentProcessingAgent",
        "document_processing_agent",
    ):
        import agents.document.document_agent as _mod

        return getattr(_mod, name)
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


__all__ = [
    "DocumentAgent",
    "document_agent",
    "DocumentProcessingAgent",
    "document_processing_agent",
]
