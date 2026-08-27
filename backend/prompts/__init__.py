"""
FinSentry AI — Phase 3D Modular Prompt System.
"""

from prompts.builder import PromptBuilder, prompt_builder
from prompts.citation import build_citation_prompt
from prompts.refusal import build_refusal_prompt
from prompts.research import build_research_prompt
from prompts.response_format import build_response_format_prompt
from prompts.system import build_system_prompt

__all__ = [
    "build_system_prompt",
    "build_research_prompt",
    "build_citation_prompt",
    "build_response_format_prompt",
    "build_refusal_prompt",
    "PromptBuilder",
    "prompt_builder",
]
