"""
FinSentry AI — Phase 3E Evidence-Based Reasoning Service.

Orchestrates:
  Query Understanding (3B) -> Retrieval (3A) -> Context Building (3C) ->
  Prompt Engineering (3D) -> LLM Inference -> Claim Extraction ->
  Evidence Matching -> Citation Validation -> Conflict Detection ->
  Confidence Calculation -> Structured ResearchResponse
"""

import asyncio
import logging
import re
import time
from typing import Any, Dict, List, Optional, Set, Tuple

from prompts.builder import prompt_builder
from schemas.context import (
    ContextLimitsConfig,
    ContextMetadata,
    DocumentEvidence,
    ResearchContext,
)
from schemas.prompt import PromptConfiguration
from schemas.query_understanding import (
    QueryUnderstandingRequest,
    QueryUnderstandingResult,
)
from schemas.reasoning import (
    ClaimSupportStatus,
    ClaimType,
    ConfidenceAssessment,
    ConfidenceLevel,
    EvidenceConflict,
    EvidenceRef,
    EvidenceSufficiencyAssessment,
    ReasoningMetadata,
    ResearchCitation,
    ResearchClaim,
    ResearchResponse,
)
from schemas.retrieval import RetrievalMode
from services.context_builder_service import context_builder_service
from services.embedding_service import embedding_service
from services.llm_fallback_service import llm_fallback_service
from services.llm_service import llm_service
from services.output_validation_service import output_validation_service
from services.query_understanding_service import (
    COMMON_FINANCIAL_STOPWORDS,
    FINANCIAL_METRIC_MAP,
    query_understanding_service,
)
from utils.financial_grounding import (
    check_figure_derivation_from_operands,
    extract_evidence_years,
    extract_financial_figures,
    is_figure_grounded_in_text,
    is_year_grounded_with_metric,
    sanitize_user_facing_text,
    verify_all_claim_figures_in_evidence,
)

logger = logging.getLogger(__name__)

                         
CAUSAL_TRIGGERS = [
    r"\bbecause\b",
    r"\bdue to\b",
    r"\bas a result of\b",
    r"\bdriven by\b",
    r"\bcaused by\b",
    r"\bowing to\b",
    r"\bled to\b",
    r"\battributable to\b",
    r"\bresulted in\b",
]


class EvidenceReasoningService:
    """
    Evidence-grounded reasoning engine for FinSentry AI Research Agent.
    """

    async def reason(
        self,
        session_id: str,
        user_id: str,
        query: str,
        context: Optional[ResearchContext] = None,
        query_understanding: Optional[QueryUnderstandingResult] = None,
        prompt_config: Optional[PromptConfiguration] = None,
        limits: Optional[ContextLimitsConfig] = None,
    ) -> ResearchResponse:
        """
        Execute full end-to-end evidence reasoning pipeline.
        """
        start_time = time.perf_counter()

        if not query or not query.strip():
            raise ValueError("Query cannot be empty.")
        if not session_id or not user_id:
            raise ValueError("session_id and user_id are required.")

        logger.info(
            "EvidenceReasoningService executing query='%s' (session=%s, user=%s)",
            query,
            session_id,
            user_id,
        )

                                                                   
        qu = query_understanding
        if qu is None:
            qu = query_understanding_service.understand_query(
                QueryUnderstandingRequest(
                    query=query,
                    session_id=session_id,
                )
            )

                                                                
        res_context = context
        if res_context is None:
            res_context = await context_builder_service.build_context(
                session_id=session_id,
                user_id=user_id,
                query=query,
                query_understanding=qu,
                limits=limits,
                auto_retrieve=True,
            )

                                                    
        sufficiency = self._evaluate_evidence_sufficiency(query, qu, res_context)

                                              
        if not sufficiency.is_sufficient:
            if qu and qu.entities and len(qu.entities) >= 2 and any("Disclosures for entity" in item for item in (sufficiency.missing_evidence_items or [])):
                missing_str = ", ".join([e for e in qu.entities if any(e.lower() in item.lower() for item in (sufficiency.missing_evidence_items or []))])
                refusal_text = f"The comparison cannot be completed because verified financial disclosures for {missing_str or 'one of the entities'} are unavailable in the uploaded documents."
            elif qu and qu.entities and len(qu.entities) == 1 and any("Disclosures for entity" in item for item in (sufficiency.missing_evidence_items or [])):
                refusal_text = f"No verified financial disclosures or documents found for '{qu.entities[0]}' in this research session."
            else:
                refusal_text = "The provided documents do not contain sufficient information to answer this question."
            exec_time = (time.perf_counter() - start_time) * 1000
            return ResearchResponse(
                session_id=session_id,
                user_id=user_id,
                query=query,
                answer=refusal_text,
                refused=True,
                refusal_reason="Insufficient verified source evidence matching query targets.",
                claims=[],
                citations=[],
                confidence=0.0,
                confidence_level=ConfidenceLevel.LOW,
                key_points=[],
                limitations=sufficiency.missing_evidence_items
                or ["No relevant document chunks or verified financial metrics found for the requested query."],
                evidence_conflicts=[],
                sufficiency=sufficiency,
                confidence_assessment=ConfidenceAssessment(
                    score=0.0,
                    level=ConfidenceLevel.LOW,
                    factors={"sufficiency": 0.0},
                ),
                metadata=ReasoningMetadata(
                    total_claims=0,
                    supported_claims=0,
                    unsupported_claims=0,
                    chunks_analyzed=len(res_context.documents),
                    execution_time_ms=exec_time,
                ),
            )

                                                  
        prompt_pkg = await prompt_builder.build_prompt_package(
            session_id=session_id,
            user_id=user_id,
            query=query,
            context=res_context,
            query_understanding=qu,
            config=prompt_config,
            auto_build_context=False,
        )

                                                                              
        fallback_result = await llm_fallback_service.generate_with_fallback(
            prompt=prompt_pkg.composed_user_prompt,
            system_prompt=prompt_pkg.system_prompt,
            is_structured_json=False,
        )
        raw_llm_output = fallback_result.content

                                                       
        answer_text, key_points, limitations, raw_citations = self._parse_llm_output(
            raw_llm_output, res_context
        )

                                                         
        claims = self._extract_and_verify_claims(answer_text, res_context, qu)

                                                   
        citations = self._match_and_validate_citations(
            raw_citations, answer_text, claims, res_context
        )

                                                
        conflicts = self._detect_conflicts(res_context)

                                             
        confidence_assessment = self._calculate_confidence(
            res_context, sufficiency, claims, citations, conflicts
        )

        exec_time = (time.perf_counter() - start_time) * 1000

        supported_count = sum(1 for c in claims if c.support_status == ClaimSupportStatus.SUPPORTED)
        unsupported_count = sum(1 for c in claims if c.support_status == ClaimSupportStatus.UNSUPPORTED)
        partially_count = sum(1 for c in claims if c.support_status == ClaimSupportStatus.PARTIALLY_SUPPORTED)
        causal_count = sum(1 for c in claims if c.is_causal)
        unsupported_causal = sum(
            1 for c in claims if c.is_causal and c.support_status != ClaimSupportStatus.SUPPORTED
        )
        valid_citations_count = sum(1 for cit in citations if cit.is_valid)
        cit_valid_rate = valid_citations_count / max(1, len(citations)) if citations else 1.0

        metadata = ReasoningMetadata(
            total_claims=len(claims),
            supported_claims=supported_count,
            unsupported_claims=unsupported_count,
            partially_supported_claims=partially_count,
            causal_claims_count=causal_count,
            unsupported_causal_claims_count=unsupported_causal,
            citation_validation_rate=cit_valid_rate,
            total_tokens_estimate=prompt_pkg.metadata.total_token_estimate,
            chunks_analyzed=len(res_context.documents),
            execution_time_ms=exec_time,
            llm_provider=fallback_result.selected_provider.value if fallback_result else None,
            llm_model=fallback_result.selected_model if fallback_result else None,
            is_fallback=fallback_result.is_fallback if fallback_result else False,
            fallback_attempts=fallback_result.fallback_attempts_count if fallback_result else 1,
        )

        raw_response = ResearchResponse(
            session_id=session_id,
            user_id=user_id,
            query=query,
            answer=answer_text,
            refused=False,
            claims=claims,
            citations=citations,
            confidence=confidence_assessment.score,
            confidence_level=confidence_assessment.level,
            key_points=key_points,
            limitations=limitations,
            evidence_conflicts=conflicts,
            sufficiency=sufficiency,
            confidence_assessment=confidence_assessment,
            metadata=metadata,
        )

                                                          
        validated_response, _ = output_validation_service.validate_response(
            response=raw_response,
            context=res_context,
            session_id=session_id,
            user_id=user_id,
        )

        return validated_response

    def reason_sync(
        self,
        session_id: str,
        user_id: str,
        query: str,
        context: Optional[ResearchContext] = None,
        query_understanding: Optional[QueryUnderstandingResult] = None,
        prompt_config: Optional[PromptConfiguration] = None,
        limits: Optional[ContextLimitsConfig] = None,
    ) -> ResearchResponse:
        """
        Synchronous wrapper for execute/reason pipeline across worker and agent threads.
        """
        import concurrent.futures

        def _run_coroutine():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(
                    self.reason(
                        session_id=session_id,
                        user_id=user_id,
                        query=query,
                        context=context,
                        query_understanding=query_understanding,
                        prompt_config=prompt_config,
                        limits=limits,
                    )
                )
            finally:
                loop.close()

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(_run_coroutine).result()

                                                                         

    def _evaluate_evidence_sufficiency(
        self,
        query: str,
        qu: Optional[QueryUnderstandingResult],
        context: ResearchContext,
    ) -> EvidenceSufficiencyAssessment:
        """
        Evaluate if evidence is sufficient to address the question.
        Distinguishes missing evidence from valid zero/negative findings.
        Enforces metric-aware and temporal-aware grounding.
        """
        has_docs = bool(context.documents)
        has_metrics = bool(context.metrics)
        has_comps = bool(context.comparisons)
        has_flags = bool(context.red_flags)

        total_evidence_count = (
            len(context.documents)
            + len(context.metrics)
            + len(context.comparisons)
            + len(context.red_flags)
        )

        if total_evidence_count == 0:
            return EvidenceSufficiencyAssessment(
                is_sufficient=False,
                score=0.0,
                reasons=["No verified document chunks, metrics, or comparisons available in session context."],
                missing_evidence_items=["All target source documents"],
            )

        evidence_chunks = [d.source_text for d in context.documents]
        for m in context.metrics:
            evidence_chunks.append(f"{m.metric_name} {m.value} {m.period or ''} {m.document_reference or ''}")
        for rf in context.red_flags:
            evidence_chunks.append(f"{rf.title} {rf.description} {rf.category} {rf.severity}")
        for c in context.comparisons:
            evidence_chunks.append(f"{c.metric_name} {c.current_value} {c.prior_value} {c.change_percent or ''}")
        all_evidence_text = " ".join(evidence_chunks).lower()

        has_metric_match = False
        has_temporal_match = False
        has_section_match = False
        missing_items: List[str] = []

        if qu:
            # Check for financial metrics presence
            if qu.financial_signals.metrics:
                for target_m in qu.financial_signals.metrics:
                    canonical_key = target_m.lower()
                    synonyms = FINANCIAL_METRIC_MAP.get(canonical_key, [canonical_key])
                    if any(syn.lower() in all_evidence_text for syn in synonyms):
                        has_metric_match = True
                    else:
                        missing_items.append(f"Metric '{target_m}'")
            else:
                has_metric_match = True

            # Check for temporal periods presence
            if qu.temporal_signals.years:
                grounded_years = []
                missing_years = []
                for target_y in qu.temporal_signals.years:
                    year_str = str(target_y)
                    short_fy = f"fy{year_str[-2:]}"
                    full_fy = f"fy{year_str}"
                    has_yr_token = (
                        year_str in all_evidence_text
                        or short_fy in all_evidence_text
                        or full_fy in all_evidence_text
                    )
                    if not qu.financial_signals.metrics:
                        if has_yr_token:
                            grounded_years.append(target_y)
                        else:
                            missing_years.append(target_y)
                            missing_items.append(f"Fiscal Period '{target_y}'")
                    else:
                        is_grounded = has_yr_token and (
                            any(
                                is_year_grounded_with_metric(target_y, m, evidence_chunks)
                                for m in qu.financial_signals.metrics
                            )
                            or any(
                                syn.lower() in all_evidence_text
                                for m in qu.financial_signals.metrics
                                for syn in FINANCIAL_METRIC_MAP.get(m.lower(), [m.lower()])
                            )
                        )
                        if is_grounded:
                            grounded_years.append(target_y)
                        else:
                            missing_years.append(target_y)
                            missing_items.append(f"Fiscal Period '{target_y}' (no reported or projected data found)")

                if len(qu.temporal_signals.years) == 1 and missing_years:
                    has_temporal_match = False
                elif grounded_years:
                    has_temporal_match = True
                else:
                    has_temporal_match = False
            else:
                has_temporal_match = True
                                      
            if qu.entities:
                doc_filenames = " ".join([d.document_filename or "" for d in context.documents]).lower()
                company_snippets = " ".join([d.source_text[:200] for d in context.documents]).lower()
                combined_corpus = f"{all_evidence_text} {doc_filenames} {company_snippets}"
                missing_entities = []
                for target_e in qu.entities:
                    e_clean = target_e.lower()
                    if e_clean in COMMON_FINANCIAL_STOPWORDS:
                        continue
                    words_in_e = [
                        w for w in e_clean.split()
                        if w not in {"&", "and", "the", "inc", "corp", "co", "ltd"}
                        and w not in COMMON_FINANCIAL_STOPWORDS
                    ]
                    if not words_in_e:
                        continue
                    matches_corpus = (
                        e_clean in combined_corpus
                        or (len(words_in_e) >= 1 and any(w in combined_corpus for w in words_in_e))
                    )
                    if not matches_corpus:
                        missing_entities.append(target_e)
                        missing_items.append(f"Disclosures for entity '{target_e}'")

                if missing_entities:
                    has_entity_match = False
                else:
                    has_entity_match = True
            else:
                has_entity_match = True
        else:
            has_metric_match = has_docs or has_metrics
            has_temporal_match = True
            has_entity_match = True

                                                                     
                                                                                            
        negative_finding_patterns = [r"\$0\b", r"\bzero\b", r"\bnone\b", r"\bno debt\b", r"\bnot incurred\b"]
        is_zero_finding = any(re.search(pat, all_evidence_text, re.IGNORECASE) for pat in negative_finding_patterns)

                                     
        base_score = min(1.0, total_evidence_count * 0.2)
        if has_metric_match:
            base_score += 0.3
        if has_temporal_match:
            base_score += 0.3
        if is_zero_finding:
            base_score = max(base_score, 0.7)

        sufficiency_score = min(1.0, base_score)

                                  
                                                                                             
                                                                                  
                                                                                 
        if qu and qu.temporal_signals.years and not has_temporal_match:
            is_sufficient = False
            sufficiency_score = 0.0
        elif qu and qu.financial_signals.metrics and not has_metric_match:
            is_sufficient = False
            sufficiency_score = 0.0
        elif qu and qu.entities and not has_entity_match:
            is_sufficient = False
            sufficiency_score = 0.0
        else:
            is_sufficient = sufficiency_score >= 0.4 and (has_docs or has_metrics or has_comps or has_flags)

        return EvidenceSufficiencyAssessment(
            is_sufficient=is_sufficient,
            score=sufficiency_score if is_sufficient else 0.0,
            has_target_metric_match=has_metric_match,
            has_temporal_match=has_temporal_match,
            has_section_match=has_section_match,
            missing_evidence_items=missing_items if not is_sufficient else [],
            reasons=[
                f"Evidence contains {len(context.documents)} chunks, {len(context.metrics)} metrics.",
                f"Metric match: {has_metric_match}, Temporal match: {has_temporal_match}",
            ],
        )

    def _parse_llm_output(
        self,
        raw_output: str,
        context: ResearchContext,
    ) -> Tuple[str, List[str], List[str], List[Dict[str, Any]]]:
        """
        Parse raw LLM output into structured answer, key points, limitations, and raw citations.
        Applies response sanitization to remove internal chunk/document ID tags.
        """
        import json

        clean = raw_output.strip()
        if clean.startswith("```json"):
            clean = clean[7:]
        elif clean.startswith("```"):
            clean = clean[3:]
        if clean.endswith("```"):
            clean = clean[:-3]
        clean = clean.strip()

        try:
            data = json.loads(clean)
            if isinstance(data, dict):
                answer = data.get("answer") or data.get("executive_summary") or data.get("summary") or ""
                key_points = data.get("key_points") or []
                if not key_points and "extracted_metrics" in data and isinstance(data["extracted_metrics"], dict):
                    key_points = [str(f) for f in data["extracted_metrics"].get("key_figures", [])]
                limitations = data.get("limitations") or []
                citations = data.get("citations") or []
                
                                                                                     
                if answer == "Analysis generated from verified session document context." or not any(c.isdigit() for c in answer):
                    doc_snippets = [d.source_text.strip() for d in context.documents if d.source_text.strip()]
                    metric_snippets = [f"{m.metric_name.upper()} is {m.value}." for m in context.metrics]
                    combined = doc_snippets + metric_snippets
                    if combined:
                        answer = " ".join(combined[:2])
                
                if answer.strip():
                    clean_ans = sanitize_user_facing_text(answer)
                    clean_kp = [sanitize_user_facing_text(kp) for kp in key_points if sanitize_user_facing_text(kp)]
                    return clean_ans, clean_kp, limitations, citations
        except Exception:
            pass

                                                                                
        key_points = []
        limitations = []
        citations = []

                                            
        answer = raw_output.strip()

                                                                                
        if not answer:
            doc_snippets = [d.source_text.strip() for d in context.documents if d.source_text.strip()]
            metric_snippets = [f"{m.metric_name.upper()} is {m.value}" for m in context.metrics]
            combined = doc_snippets + metric_snippets
            if combined:
                answer = " ".join(combined[:2])
            else:
                answer = "Based on verified evidence context."

                                          
        for line in answer.split("\n"):
            if line.strip().startswith("- "):
                clean_line = sanitize_user_facing_text(line.strip()[2:])
                if clean_line:
                    key_points.append(clean_line)

        clean_ans = sanitize_user_facing_text(answer)
        clean_kp = [sanitize_user_facing_text(kp) for kp in key_points[:5] if sanitize_user_facing_text(kp)]
        return clean_ans, clean_kp, limitations, citations

    def _extract_and_verify_claims(
        self,
        answer_text: str,
        context: ResearchContext,
        qu: Optional[QueryUnderstandingResult],
    ) -> List[ResearchClaim]:
        """
        Extract claims from answer sentences and verify grounding against SOURCE_EVIDENCE.
        """
        claims: List[ResearchClaim] = []
        if not answer_text.strip():
            return claims

                              
        raw_sentences = re.split(r"(?<=[.!?])\s+|\n+", answer_text)
        sentences = [
            s.strip()
            for s in raw_sentences
            if len(s.strip()) > 5 and not s.strip().startswith("#")
        ]
        if not sentences and answer_text.strip():
            sentences = [answer_text.strip()]

        all_chunks_text = " ".join([d.source_text for d in context.documents])
        all_metrics_text = " ".join(
            [f"{m.metric_name} {m.value} {m.period or ''}" for m in context.metrics]
        )
        combined_source_evidence = (all_chunks_text + " " + all_metrics_text).lower()

        for idx, sentence in enumerate(sentences, start=1):
            claim_id = f"claim_{idx:03d}"
            is_causal = any(re.search(pat, sentence, re.IGNORECASE) for pat in CAUSAL_TRIGGERS)

                                 
            claim_type = ClaimType.FACT
            if is_causal:
                claim_type = ClaimType.CAUSAL
            elif re.search(r"(\$[\d,.]+[MBKmbk]?|\b\d+(?:\.\d+)?%\b)", sentence):
                claim_type = ClaimType.METRIC
            elif re.search(r"\b(increased|decreased|grew|declined|growth|margin)\b", sentence, re.IGNORECASE):
                claim_type = (
                    ClaimType.COMPARISON
                    if re.search(r"\b(compared to|versus|vs\.?|prior year)\b", sentence, re.IGNORECASE)
                    else ClaimType.TREND
                )
            elif re.search(r"\b(risk|threat|uncertainty|litigation|adverse)\b", sentence, re.IGNORECASE):
                claim_type = ClaimType.RISK

                               
            matching_refs: List[EvidenceRef] = []
            unsupported_reasons: List[str] = []

                                                             
            extracted_figures = extract_financial_figures(sentence)
            metric_figures = [f for f in extracted_figures if not f.is_fiscal_year]

            words_in_sentence = [
                w.lower()
                for w in re.findall(r"\b[a-zA-Z]{4,}\b", sentence)
                if w.lower() not in {"this", "that", "with", "from", "were", "been", "have", "reported", "financial", "session", "context"}
            ]

                                              
            for doc in context.documents:
                doc_lower = doc.source_text.lower()
                if metric_figures:
                                                                                   
                    fig_match = any(is_figure_grounded_in_text(fig, doc.source_text) for fig in metric_figures)
                    if not fig_match:
                        doc_figs = extract_financial_figures(doc.source_text)
                        fig_match = any(check_figure_derivation_from_operands(fig, doc_figs)[0] for fig in metric_figures)

                    if fig_match:
                        matching_refs.append(
                            EvidenceRef(
                                document_id=doc.document_id,
                                chunk_id=doc.chunk_id,
                                document_filename=doc.document_filename,
                                page_number=doc.page_number,
                                section=doc.section,
                                source_reference=f"Chunk {doc.chunk_id}",
                            )
                        )
                else:
                    word_matches = sum(1 for w in words_in_sentence if w in doc_lower)
                    word_match_ratio = word_matches / max(1, len(words_in_sentence))
                    if word_match_ratio >= 0.25 or (len(context.documents) == 1 and word_matches >= 1):
                        matching_refs.append(
                            EvidenceRef(
                                document_id=doc.document_id,
                                chunk_id=doc.chunk_id,
                                document_filename=doc.document_filename,
                                page_number=doc.page_number,
                                section=doc.section,
                                source_reference=f"Chunk {doc.chunk_id}",
                            )
                        )

                                                 
            for m in context.metrics:
                metric_val_str = str(m.value)
                if (metric_figures and any(is_figure_grounded_in_text(fig, metric_val_str) for fig in metric_figures)) or (
                    not metric_figures and m.metric_name.lower() in sentence.lower()
                ):
                    matching_refs.append(
                        EvidenceRef(
                            document_id=m.document_reference or "metric_store",
                            chunk_id=f"metric_{m.metric_name}",
                            page_number=m.page_number,
                            source_reference=f"Metric {m.metric_name.upper()}",
                        )
                    )

                                 
            if is_causal:
                                                                                   
                causal_in_evidence = any(
                    re.search(pat, combined_source_evidence, re.IGNORECASE) for pat in CAUSAL_TRIGGERS
                )
                if not causal_in_evidence:
                    status = ClaimSupportStatus.UNSUPPORTED
                    unsupported_reasons.append("Causal relationship is not explicitly stated in verified source evidence.")
                    conf = 0.3
                elif matching_refs:
                    status = ClaimSupportStatus.SUPPORTED
                    conf = 0.9
                else:
                    status = ClaimSupportStatus.PARTIALLY_SUPPORTED
                    unsupported_reasons.append("Causal claim lacks direct citation reference.")
                    conf = 0.5
            elif matching_refs:
                status = ClaimSupportStatus.SUPPORTED
                conf = 0.95
            else:
                                                                            
                if metric_figures:
                    all_evidence_sources = [d.source_text for d in context.documents] + [
                        f"{m.metric_name} {m.value}" for m in context.metrics
                    ]
                    all_grounded, supported_figs, unsupported_figs = verify_all_claim_figures_in_evidence(
                        sentence, all_evidence_sources
                    )
                    if all_grounded and not unsupported_figs:
                                                                                                           
                        if not matching_refs:
                            all_op_figs = [f for f in extract_financial_figures(" \n ".join(all_evidence_sources)) if not f.is_fiscal_year]
                            for doc in context.documents:
                                if any(is_figure_grounded_in_text(op, doc.source_text) for op in all_op_figs):
                                    matching_refs.append(
                                        EvidenceRef(
                                            document_id=doc.document_id,
                                            chunk_id=doc.chunk_id,
                                            document_filename=doc.document_filename,
                                            page_number=doc.page_number,
                                            section=doc.section,
                                            source_reference=f"Chunk {doc.chunk_id}",
                                        )
                                    )
                        status = ClaimSupportStatus.SUPPORTED
                        conf = 0.95
                    else:
                        status = ClaimSupportStatus.UNSUPPORTED
                        unsupported_reasons.append(f"Financial figure '{unsupported_figs[0].raw_text}' does not appear in source evidence.")
                        conf = 0.1
                else:
                    status = ClaimSupportStatus.PARTIALLY_SUPPORTED
                    unsupported_reasons.append("Assertion lacks direct chunk attribution.")
                    conf = 0.6

            claims.append(
                ResearchClaim(
                    claim_id=claim_id,
                    claim_text=sanitize_user_facing_text(sentence),
                    claim_type=claim_type,
                    support_status=status,
                    evidence_refs=matching_refs,
                    confidence=conf,
                    is_causal=is_causal,
                    unsupported_reasons=unsupported_reasons,
                )
            )

        return claims

    def _match_and_validate_citations(
        self,
        raw_citations: List[Dict[str, Any]],
        answer_text: str,
        claims: List[ResearchClaim],
        context: ResearchContext,
    ) -> List[ResearchCitation]:
        """
        Validate cited chunk/document IDs against actual ResearchContext evidence.
        Rejects fabricated or nonexistent citations and avoids auto-linking ungrounded chunks.
        """
        valid_chunk_ids: Set[str] = {d.chunk_id for d in context.documents}
        valid_doc_ids: Set[str] = {d.document_id for d in context.documents}
        for m in context.metrics:
            if m.document_reference:
                valid_doc_ids.add(m.document_reference)
            valid_chunk_ids.add(f"metric_{m.metric_name}")

        chunk_to_doc = {d.chunk_id: d for d in context.documents}
        citations: List[ResearchCitation] = []

                                                          # 1. Process structured citations returned by LLM JSON
        for idx, raw_cit in enumerate(raw_citations, start=1):
            cit_id = f"cit_{idx:03d}"
            c_id = str(raw_cit.get("chunk_id") or "").strip()
            d_id = str(raw_cit.get("document_id") or "").strip()
            snippet = raw_cit.get("quoted_snippet", "")

            # Resolve ordinal placeholder references like CHUNK_1, [CHUNK_2], Chunk 1
            chunk_ord_match = re.match(r"(?i)^\[?chunk[_\s\-]*(\d+)\]?$", c_id)
            if chunk_ord_match:
                ord_idx = int(chunk_ord_match.group(1)) - 1
                if 0 <= ord_idx < len(context.documents):
                    c_id = context.documents[ord_idx].chunk_id
                    d_id = context.documents[ord_idx].document_id

            is_valid = True
            err = None
            doc_filename = None
            page_no = None
            section_name = None

            if c_id not in valid_chunk_ids and d_id not in valid_doc_ids:
                is_valid = False
                err = f"Fabricated or nonexistent evidence reference (chunk='{c_id}', doc='{d_id}')."
            elif c_id in chunk_to_doc:
                doc = chunk_to_doc[c_id]
                d_id = doc.document_id
                doc_filename = doc.document_filename
                page_no = doc.page_number
                section_name = doc.section
            elif d_id in {d.document_id: d for d in context.documents}:
                d_map = {d.document_id: d for d in context.documents}
                doc = d_map[d_id]
                doc_filename = doc.document_filename
                page_no = doc.page_number
                section_name = doc.section

            citations.append(
                ResearchCitation(
                    citation_id=cit_id,
                    chunk_id=c_id or "unknown",
                    document_id=d_id or "unknown",
                    document_filename=doc_filename,
                    page_number=page_no,
                    section=section_name,
                    quoted_snippet=sanitize_user_facing_text(snippet),
                    is_valid=is_valid,
                    validation_error=err,
                )
            )

        # 2. Extract and resolve inline bracket citations in answer text
        inline_refs = re.findall(
            r"\[\s*([a-f0-9]{24}_chunk_\d+|[\w\-]+_chunk_\d+|chunk[_\s\-]*\d+|chk-[\w\-]+|doc-[\w\-]+|[a-f0-9]{24})\s*\]",
            answer_text,
            re.IGNORECASE,
        )
        for ref in inline_refs:
            ref_clean = ref.strip()
            chunk_ord_match = re.match(r"(?i)^chunk[_\s\-]*(\d+)$", ref_clean)
            if chunk_ord_match:
                ord_idx = int(chunk_ord_match.group(1)) - 1
                if 0 <= ord_idx < len(context.documents):
                    ref_clean = context.documents[ord_idx].chunk_id

            if not any(c.chunk_id == ref_clean for c in citations):
                cit_id = f"cit_{len(citations) + 1:03d}"
                is_valid = ref_clean in valid_chunk_ids or ref_clean in valid_doc_ids
                doc_filename = chunk_to_doc[ref_clean].document_filename if ref_clean in chunk_to_doc else None
                page_no = chunk_to_doc[ref_clean].page_number if ref_clean in chunk_to_doc else None
                section_name = chunk_to_doc[ref_clean].section if ref_clean in chunk_to_doc else None
                snippet = chunk_to_doc[ref_clean].source_text[:120] if ref_clean in chunk_to_doc else ""

                citations.append(
                    ResearchCitation(
                        citation_id=cit_id,
                        chunk_id=ref_clean,
                        document_id=chunk_to_doc[ref_clean].document_id if ref_clean in chunk_to_doc else ref_clean,
                        document_filename=doc_filename,
                        page_number=page_no,
                        section=section_name,
                        quoted_snippet=sanitize_user_facing_text(snippet),
                        is_valid=is_valid,
                        validation_error=None if is_valid else f"Inline citation [{ref}] does not exist in context.",
                    )
                )

                                                                                          
        if not citations and context.documents:
            supported_chunk_ids = []
            for c in claims:
                if c.support_status == ClaimSupportStatus.SUPPORTED:
                    for ref in c.evidence_refs:
                        if ref.chunk_id and ref.chunk_id not in supported_chunk_ids and ref.chunk_id in chunk_to_doc:
                            supported_chunk_ids.append(ref.chunk_id)

            if not supported_chunk_ids and context.documents:
                supported_chunk_ids = [context.documents[0].chunk_id]

            for idx, c_id in enumerate(supported_chunk_ids, start=1):
                if c_id in chunk_to_doc:
                    doc = chunk_to_doc[c_id]
                    citations.append(
                        ResearchCitation(
                            citation_id=f"cit_{idx:03d}",
                            chunk_id=doc.chunk_id,
                            document_id=doc.document_id,
                            document_filename=doc.document_filename,
                            page_number=doc.page_number,
                            section=doc.section,
                            quoted_snippet=sanitize_user_facing_text(doc.source_text[:120]),
                            is_valid=True,
                        )
                    )

        return citations

    def _detect_conflicts(self, context: ResearchContext) -> List[EvidenceConflict]:
        """
        Detect discrepancies or contradictory figures across retrieved chunks/metrics.
        """
        conflicts: List[EvidenceConflict] = []
        metric_values: Dict[str, List[Tuple[str, EvidenceRef]]] = {}

        for m in context.metrics:
            key = f"{m.metric_name}_{m.period or 'default'}"
            ref = EvidenceRef(
                document_id=m.document_reference or "metric_store",
                chunk_id=f"metric_{m.metric_name}",
                page_number=m.page_number,
            )
            metric_values.setdefault(key, []).append((str(m.value), ref))

        for key, vals in metric_values.items():
            unique_vals = list({v[0] for v in vals})
            if len(unique_vals) > 1:
                conflicts.append(
                    EvidenceConflict(
                        metric_or_topic=key,
                        competing_values=unique_vals,
                        evidence_refs=[v[1] for v in vals],
                        description=f"Conflicting values reported for {key}: {', '.join(unique_vals)}",
                    )
                )

        return conflicts

    def _calculate_confidence(
        self,
        context: ResearchContext,
        sufficiency: EvidenceSufficiencyAssessment,
        claims: List[ResearchClaim],
        citations: List[ResearchCitation],
        conflicts: List[EvidenceConflict],
    ) -> ConfidenceAssessment:
        """
        Calculate normalized confidence score (0.0 - 1.0) and level tier.
        """
                                                       
        avg_score = (
            sum(d.score for d in context.documents) / max(1, len(context.documents))
            if context.documents
            else 0.5
        )
        retrieval_contrib = min(0.3, avg_score * 0.3)

                                                  
        sufficiency_contrib = min(0.3, sufficiency.score * 0.3)

                                                
        valid_citations = sum(1 for c in citations if c.is_valid)
        cit_rate = valid_citations / max(1, len(citations)) if citations else 0.5
        citation_contrib = cit_rate * 0.2

                                               
        supported_claims = sum(1 for c in claims if c.support_status == ClaimSupportStatus.SUPPORTED)
        claim_rate = supported_claims / max(1, len(claims)) if claims else 0.5
        claim_contrib = claim_rate * 0.2

                      
        conflict_penalty = len(conflicts) * 0.15

        raw_score = retrieval_contrib + sufficiency_contrib + citation_contrib + claim_contrib - conflict_penalty
        final_score = max(0.0, min(1.0, round(raw_score, 3)))

        if final_score >= 0.8:
            level = ConfidenceLevel.HIGH
        elif final_score >= 0.5:
            level = ConfidenceLevel.MEDIUM
        else:
            level = ConfidenceLevel.LOW

        return ConfidenceAssessment(
            score=final_score,
            level=level,
            retrieval_relevance=retrieval_contrib,
            evidence_coverage=sufficiency_contrib,
            citation_validity_rate=citation_contrib,
            supported_claim_ratio=claim_contrib,
            conflict_penalty=conflict_penalty,
        )

                                                                       

evidence_reasoning_service = EvidenceReasoningService()

