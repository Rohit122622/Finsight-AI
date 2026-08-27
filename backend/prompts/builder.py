"""
FinSentry AI — Phase 3D Prompt Builder.

Assembles modular prompt components into a structured, validated PromptPackage:
  1. System behavior prompt
  2. Research context payload
  3. Citation instructions
  4. Response format schema
  5. Refusal behavior rules
  6. Operational sizing metadata and section breakdowns
"""

import logging
from typing import Dict, List, Optional

from prompts.citation import build_citation_prompt
from prompts.refusal import build_refusal_prompt
from prompts.research import build_research_prompt
from prompts.response_format import build_response_format_prompt
from prompts.system import build_system_prompt
from schemas.context import ContextLimitsConfig, ResearchContext
from schemas.prompt import (
    PromptConfiguration,
    PromptMetadata,
    PromptPackage,
    PromptSection,
    PromptVersion,
)
from schemas.query_understanding import QueryUnderstandingResult
from services.context_builder_service import context_builder_service

logger = logging.getLogger(__name__)


class PromptBuilder:
    """
    Modular prompt engineering service for the FinSentry Research Agent.
    Prepares prompts for Phase 3E reasoning; does not execute LLM inference.
    """

    def __init__(self, default_config: Optional[PromptConfiguration] = None) -> None:
        self.default_config = default_config or PromptConfiguration()

    async def build_prompt_package(
        self,
        session_id: str,
        user_id: str,
        query: str,
        context: Optional[ResearchContext] = None,
        query_understanding: Optional[QueryUnderstandingResult] = None,
        config: Optional[PromptConfiguration] = None,
        limits: Optional[ContextLimitsConfig] = None,
        auto_build_context: bool = True,
    ) -> PromptPackage:
        """
        Assemble the complete, modular prompt package.

        Args:
            session_id: Research session identifier.
            user_id: Owning user identifier.
            query: User question.
            context: Pre-built ResearchContext (optional).
            query_understanding: Pre-computed QueryUnderstandingResult (optional).
            config: Custom PromptConfiguration (optional).
            limits: Custom context window limits if auto-building context.
            auto_build_context: If True and context is None, calls ContextBuilderService.

        Returns:
            Structured PromptPackage envelope.
        """
        cfg = config or self.default_config

                                                    
        res_context = context
        if res_context is None:
            if auto_build_context:
                res_context = await context_builder_service.build_context(
                    session_id=session_id,
                    user_id=user_id,
                    query=query,
                    query_understanding=query_understanding,
                    limits=limits,
                    auto_retrieve=True,
                )
            else:
                                       
                res_context = await context_builder_service.build_context(
                    session_id=session_id,
                    user_id=user_id,
                    query=query,
                    query_understanding=query_understanding,
                    retrieved_results=[],
                    auto_retrieve=False,
                )

        qu = query_understanding or res_context.query_understanding

                                                
        system_text = build_system_prompt(cfg)
        research_text = build_research_prompt(
            query=query,
            context=res_context,
            query_understanding=qu,
            config=cfg,
        )
        citation_text = build_citation_prompt(cfg)
        format_text = build_response_format_prompt(cfg)
        refusal_text = build_refusal_prompt(cfg)

                                                                 
        composed_user_parts = [
            "TASK INSTRUCTIONS:",
            "Analyze the provided research context and answer the user question following the citation, response format, and refusal rules below.\n",
            research_text,
            "\n" + citation_text,
            "\n" + refusal_text,
            "\n" + format_text,
        ]
        composed_user_prompt = "\n".join(composed_user_parts)

                                             
        sections: List[PromptSection] = [
            PromptSection(
                name="system",
                version=cfg.version.value,
                content=system_text,
                character_count=len(system_text),
                token_estimate=self._estimate_tokens(system_text),
            ),
            PromptSection(
                name="research",
                version=cfg.version.value,
                content=research_text,
                character_count=len(research_text),
                token_estimate=self._estimate_tokens(research_text),
            ),
            PromptSection(
                name="citation",
                version=cfg.version.value,
                content=citation_text,
                character_count=len(citation_text),
                token_estimate=self._estimate_tokens(citation_text),
            ),
            PromptSection(
                name="response_format",
                version=cfg.version.value,
                content=format_text,
                character_count=len(format_text),
                token_estimate=self._estimate_tokens(format_text),
            ),
            PromptSection(
                name="refusal",
                version=cfg.version.value,
                content=refusal_text,
                character_count=len(refusal_text),
                token_estimate=self._estimate_tokens(refusal_text),
            ),
        ]

        section_breakdown = {s.name: s.token_estimate for s in sections}
        total_chars = len(system_text) + len(composed_user_prompt)
        total_tokens = self._estimate_tokens(system_text) + self._estimate_tokens(composed_user_prompt)

        metadata = PromptMetadata(
            version=cfg.version.value,
            total_characters=total_chars,
            total_token_estimate=total_tokens,
            section_breakdown=section_breakdown,
            has_source_evidence=bool(res_context.documents or res_context.metrics or res_context.red_flags or res_context.comparisons),
            has_conversation_context=bool(res_context.chat_history),
            has_session_memory=res_context.session_memory is not None,
            has_query_understanding=qu is not None,
            evidence_chunks_count=len(res_context.documents),
            metrics_count=len(res_context.metrics),
            red_flags_count=len(res_context.red_flags),
            comparisons_count=len(res_context.comparisons),
            history_messages_count=len(res_context.chat_history),
        )

        package = PromptPackage(
            session_id=session_id,
            user_id=user_id,
            system_prompt=system_text,
            research_prompt=research_text,
            citation_prompt=citation_text,
            response_format_prompt=format_text,
            refusal_prompt=refusal_text,
            composed_user_prompt=composed_user_prompt,
            sections=sections,
            config=cfg,
            metadata=metadata,
        )

        logger.info(
            "PromptPackage assembled (session=%s, user=%s, version=%s, total_tokens=%d, chunks=%d)",
            session_id,
            user_id,
            cfg.version.value,
            total_tokens,
            len(res_context.documents),
        )

        return package

    def _estimate_tokens(self, text: str) -> int:
        """Deterministic token count approximation (1.3 tokens per whitespace-separated word)."""
        words = text.split()
        return max(1, int(len(words) * 1.3))


                                                                       

prompt_builder = PromptBuilder()
