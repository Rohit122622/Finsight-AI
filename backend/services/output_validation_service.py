"""
FinSentry AI — Phase 3G Output Validation Service.

Production-grade multi-stage validation layer for Research Agent responses.
Guarantees:
  1. Strict Pydantic structure & schema compliance
  2. Authoritative claim-level grounding & verification
  3. Strict citation validation (anti-hallucination & multi-tenant isolation)
  4. Material claim citation completeness
  5. Deterministic confidence calibration & tier consistency
  6. Redundant/duplicate answer & claim deduplication
  7. Deterministic refusal safety & distinction of negative findings
  8. Multi-tenant and cross-session isolation enforcement
  9. Prompt-injection defense & security sanitization
"""

import logging
import re
import string
from typing import Any, Dict, List, Optional, Set, Tuple
from pydantic import ValidationError

from schemas.context import ResearchContext
from schemas.output_validation import (
    OutputValidationConfig,
    ValidationResult,
    ValidationStatus,
)
from schemas.reasoning import (
    ClaimSupportStatus,
    ClaimType,
    ConfidenceAssessment,
    ConfidenceLevel,
    EvidenceRef,
    ReasoningMetadata,
    ResearchCitation,
    ResearchClaim,
    ResearchResponse,
)

from utils.financial_grounding import (
    extract_financial_figures,
    is_figure_grounded_in_text,
    sanitize_user_facing_text,
    verify_all_claim_figures_in_evidence,
)

logger = logging.getLogger(__name__)

                              
STANDARD_REFUSAL_TEXT = "The provided documents do not contain sufficient information to answer this question."

                             
PROMPT_INJECTION_PATTERNS = [
    r"ignore (all )?previous instructions",
    r"disregard (all )?previous rules",
    r"system prompt override",
    r"you are now in developer mode",
    r"bypass safety guidelines",
    r"ignore citation requirements",
]

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


class OutputValidationService:
    """
    Validation engine ensuring every Research Agent response is safe,
    structurally sound, grounded in verified context, and isolated per tenant.
    """

    def __init__(self, default_config: Optional[OutputValidationConfig] = None) -> None:
        self.default_config = default_config or OutputValidationConfig()

    def validate_response(
        self,
        response: Any,
        context: Optional[ResearchContext] = None,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        config: Optional[OutputValidationConfig] = None,
    ) -> Tuple[ResearchResponse, ValidationResult]:
        """
        Execute full Phase 3G Output Validation pipeline on a Research Agent response.

        Args:
            response: ResearchResponse instance or raw dict
            context: ResearchContext containing authoritative source evidence
            session_id: Expected session ID for tenant isolation
            user_id: Expected user ID for tenant isolation
            config: Optional validation policy overrides

        Returns:
            Tuple of (Sanitized/Validated ResearchResponse, Structured ValidationResult)
        """
        cfg = config or self.default_config
        errors: List[str] = []
        warnings: List[str] = []
        duplicate_claims: List[str] = []
        duplicate_citations: List[str] = []
        duplicate_count = 0

                                                                        
        validated_envelope, struct_errors = self._validate_structure(response)
        if struct_errors:
            errors.extend(struct_errors)

        if validated_envelope is None:
                                                                         
            logger.error("Phase 3G: Fatal structure validation failure: %s", errors)
            sid = session_id or "unknown"
            uid = user_id or "unknown"
            q = "Research query"
            if isinstance(response, dict):
                sid = response.get("session_id", sid)
                uid = response.get("user_id", uid)
                q = response.get("query", q)

            refused_resp = ResearchResponse(
                session_id=sid,
                user_id=uid,
                query=q,
                answer=STANDARD_REFUSAL_TEXT,
                refused=True,
                refusal_reason=f"Structured output schema validation failed: {'; '.join(errors)}",
                claims=[],
                citations=[],
                confidence=0.0,
                confidence_level=ConfidenceLevel.LOW,
                key_points=[],
                limitations=["Response violated strict Pydantic contract"],
                confidence_assessment=ConfidenceAssessment(score=0.0, level=ConfidenceLevel.LOW),
                metadata=ReasoningMetadata(execution_time_ms=0.0),
            )
            result = ValidationResult(
                valid=False,
                status=ValidationStatus.INVALID,
                validation_errors=errors,
                validation_warnings=warnings,
                final_confidence=0.0,
                confidence_level=ConfidenceLevel.LOW,
                refusal_required=True,
                refusal_reason=refused_resp.refusal_reason,
            )
            return refused_resp, result

                                  
        resp = validated_envelope

                                                                        
        active_session_id = session_id or resp.session_id
        active_user_id = user_id or resp.user_id

        if resp.session_id != active_session_id:
            errors.append(f"Session ID mismatch: response='{resp.session_id}' vs session='{active_session_id}'")
        if resp.user_id != active_user_id:
            errors.append(f"User ID mismatch: response='{resp.user_id}' vs user='{active_user_id}'")

                                                                        
        if resp.refused:
            if not resp.refusal_reason or not resp.refusal_reason.strip():
                errors.append("Refused response must contain a non-empty refusal_reason.")
                resp.refusal_reason = "Insufficient authoritative evidence in provided context."

            resp.answer = STANDARD_REFUSAL_TEXT
            resp.confidence = 0.0
            resp.confidence_level = ConfidenceLevel.LOW
            resp.confidence_assessment.score = 0.0
            resp.confidence_assessment.level = ConfidenceLevel.LOW
            resp.citations = []
            resp.key_points = []

            result = ValidationResult(
                valid=len(errors) == 0,
                status=ValidationStatus.REFUSED if len(errors) == 0 else ValidationStatus.INVALID,
                validation_errors=errors,
                validation_warnings=warnings,
                final_confidence=0.0,
                confidence_level=ConfidenceLevel.LOW,
                refusal_required=True,
                refusal_reason=resp.refusal_reason,
            )
            return resp, result

                                                                        
        combined_text = f"{resp.answer} {' '.join(resp.key_points)}"
        for pat in PROMPT_INJECTION_PATTERNS:
            if re.search(pat, combined_text, re.IGNORECASE):
                errors.append(f"Potential prompt injection pattern detected in answer: '{pat}'")

                                                                        
        if cfg.deduplicate_answer_text and resp.answer:
            deduped_answer, removed_sentences = self._deduplicate_answer_text(resp.answer)
            if removed_sentences > 0:
                resp.answer = deduped_answer
                duplicate_count += removed_sentences
                warnings.append(f"Deduplicated {removed_sentences} redundant sentence loop(s) in answer text.")

                                                                        
        valid_citations, invalid_cits, dup_cits = self._validate_citations(
            citations=resp.citations,
            context=context,
            session_id=active_session_id,
            user_id=active_user_id,
            cfg=cfg,
        )
        resp.citations = valid_citations
        validated_citation_count = len(valid_citations)
        invalid_citation_count = len(invalid_cits)
        duplicate_citations.extend(dup_cits)
        duplicate_count += len(dup_cits)

        if invalid_citation_count > 0:
            for inv in invalid_cits:
                msg = f"Invalid citation rejected: citation_id='{inv.citation_id}', chunk_id='{inv.chunk_id}': {inv.validation_error}"
                warnings.append(msg)

                                                                        
        validated_claims, dup_claims = self._validate_claims(
            claims=resp.claims,
            context=context,
            cfg=cfg,
        )
        resp.claims = validated_claims
        duplicate_claims.extend(dup_claims)
        duplicate_count += len(dup_claims)

        supported_count = sum(1 for c in resp.claims if c.support_status == ClaimSupportStatus.SUPPORTED)
        unsupported_count = sum(1 for c in resp.claims if c.support_status == ClaimSupportStatus.UNSUPPORTED)
        partially_count = sum(1 for c in resp.claims if c.support_status == ClaimSupportStatus.PARTIALLY_SUPPORTED)
        total_claims = len(resp.claims)

                                                            
        for claim in resp.claims:
            is_material = claim.claim_type in [ClaimType.METRIC, ClaimType.TREND, ClaimType.COMPARISON, ClaimType.CAUSAL]
            if is_material and not claim.evidence_refs and claim.support_status == ClaimSupportStatus.SUPPORTED:
                claim.support_status = ClaimSupportStatus.UNSUPPORTED
                claim.confidence = min(claim.confidence, 0.2)
                claim.unsupported_reasons.append("Material financial claim lacks direct citation reference.")
                unsupported_count += 1
                supported_count = max(0, supported_count - 1)

                                                                        
        refusal_required = False
        refusal_reason = None

                                                                                               
        if context is not None and not context.documents and not context.metrics:
            is_negative_finding = self._is_explicit_negative_finding(resp.answer, context)
            if not is_negative_finding:
                refusal_required = True
                refusal_reason = "Insufficient verified source evidence in session context to answer query."

                                       
        if total_claims > 0:
            unsupported_ratio = unsupported_count / total_claims
            if unsupported_ratio > cfg.unsupported_claims_tolerance and not refusal_required:
                refusal_required = True
                refusal_reason = f"High ratio of unsupported claims ({unsupported_count}/{total_claims}). Safety policy triggered refusal."

                                                                           
        if cfg.refuse_on_unsupported_causal and any(c.is_causal and c.support_status == ClaimSupportStatus.UNSUPPORTED for c in resp.claims):
            if total_claims == 1 or unsupported_count == total_claims:
                refusal_required = True
                refusal_reason = "Causal assertion lacks explicit supporting evidence in source documents."

        if cfg.refuse_on_unsupported_metrics and any(c.claim_type == ClaimType.METRIC and c.support_status == ClaimSupportStatus.UNSUPPORTED for c in resp.claims):
            if total_claims == 1 or unsupported_count == total_claims:
                refusal_required = True
                refusal_reason = "Key financial metric assertions could not be grounded in verified source evidence."

        if refusal_required:
            resp.refused = True
            resp.refusal_reason = refusal_reason or "Insufficient verified source evidence to support analytical answer."
            resp.answer = STANDARD_REFUSAL_TEXT
            resp.confidence = 0.0
            resp.confidence_level = ConfidenceLevel.LOW
            resp.confidence_assessment.score = 0.0
            resp.confidence_assessment.level = ConfidenceLevel.LOW
            resp.citations = []
            resp.key_points = []

            result = ValidationResult(
                valid=True,
                status=ValidationStatus.REFUSED,
                validation_errors=errors,
                validation_warnings=warnings,
                validated_claim_count=total_claims,
                supported_claim_count=supported_count,
                unsupported_claim_count=unsupported_count,
                partially_supported_claim_count=partially_count,
                validated_citation_count=0,
                invalid_citation_count=invalid_citation_count,
                duplicate_count=duplicate_count,
                final_confidence=0.0,
                confidence_level=ConfidenceLevel.LOW,
                refusal_required=True,
                refusal_reason=resp.refusal_reason,
                duplicate_claims=duplicate_claims,
                duplicate_citations=duplicate_citations,
            )
            return resp, result

                                                                       
        calibrated_conf, cal_level, conf_warnings = self._validate_and_calibrate_confidence(
            resp=resp,
            supported_claims=supported_count,
            unsupported_claims=unsupported_count,
            invalid_citations=invalid_citation_count,
            cfg=cfg,
        )
        warnings.extend(conf_warnings)
        resp.confidence = calibrated_conf
        resp.confidence_level = cal_level
        resp.confidence_assessment.score = calibrated_conf
        resp.confidence_assessment.level = cal_level

                                                                       
        is_valid = len(errors) == 0
        status = ValidationStatus.VALID if is_valid else ValidationStatus.INVALID
        if duplicate_count > 0 and is_valid:
            status = ValidationStatus.MODIFIED

                                                       
        resp.answer = sanitize_user_facing_text(resp.answer)
        resp.key_points = [sanitize_user_facing_text(kp) for kp in resp.key_points if sanitize_user_facing_text(kp)]
        for claim in resp.claims:
            claim.claim_text = sanitize_user_facing_text(claim.claim_text)
        for cit in resp.citations:
            cit.quoted_snippet = sanitize_user_facing_text(cit.quoted_snippet)

        resp.metadata.total_claims = len(resp.claims)
        resp.metadata.supported_claims = supported_count
        resp.metadata.unsupported_claims = unsupported_count
        resp.metadata.partially_supported_claims = partially_count

        result = ValidationResult(
            valid=is_valid,
            status=status,
            validation_errors=errors,
            validation_warnings=warnings,
            validated_claim_count=len(resp.claims),
            supported_claim_count=supported_count,
            unsupported_claim_count=unsupported_count,
            partially_supported_claim_count=partially_count,
            validated_citation_count=validated_citation_count,
            invalid_citation_count=invalid_citation_count,
            duplicate_count=duplicate_count,
            final_confidence=calibrated_conf,
            confidence_level=cal_level,
            refusal_required=False,
            refusal_reason=None,
            duplicate_claims=duplicate_claims,
            duplicate_citations=duplicate_citations,
            metadata={
                "strict_mode": cfg.strict_mode,
                "invalid_citations_rejected": invalid_citation_count,
            },
        )

        return resp, result

                                                                         

    def _validate_structure(self, response: Any) -> Tuple[Optional[ResearchResponse], List[str]]:
        """Validate input against strict ResearchResponse Pydantic schema."""
        errors: List[str] = []

        if isinstance(response, ResearchResponse):
                                                                            
            if response.confidence < 0.0 or response.confidence > 1.0:
                errors.append(f"Confidence score {response.confidence} is outside valid [0.0, 1.0] range.")
            return response, errors

        if isinstance(response, dict):
                                   
            required_fields = ["answer", "claims", "citations", "confidence", "confidence_level"]
            for f in required_fields:
                if f not in response:
                    errors.append(f"Missing required field: '{f}'")

                                         
            if "confidence" in response:
                try:
                    c_val = float(response["confidence"])
                    if c_val < 0.0 or c_val > 1.0:
                        errors.append(f"Confidence score {c_val} is outside [0.0, 1.0] bounds.")
                except (ValueError, TypeError):
                    errors.append(f"Invalid confidence type: '{response['confidence']}'")

            try:
                parsed = ResearchResponse.model_validate(response)
                return parsed, errors
            except ValidationError as ve:
                for err in ve.errors():
                    field_path = " -> ".join(str(loc) for loc in err["loc"])
                    errors.append(f"Field '{field_path}': {err['msg']}")
                return None, errors
            except Exception as exc:
                errors.append(f"Schema parsing error: {exc}")
                return None, errors

        errors.append(f"Response must be a ResearchResponse or dict, got {type(response).__name__}")
        return None, errors

    def _validate_citations(
        self,
        citations: List[ResearchCitation],
        context: Optional[ResearchContext],
        session_id: str,
        user_id: str,
        cfg: OutputValidationConfig,
    ) -> Tuple[List[ResearchCitation], List[ResearchCitation], List[str]]:
        """Validate citations against context, rejecting fabricated or foreign citations."""
        valid_citations: List[ResearchCitation] = []
        invalid_citations: List[ResearchCitation] = []
        duplicate_citations: List[str] = []
        seen_keys: Set[str] = set()

                                                                   
        valid_chunk_ids: Set[str] = set()
        valid_doc_ids: Set[str] = set()
        chunk_to_meta: Dict[str, Dict[str, Any]] = {}

        if context is not None:
            for doc in context.documents:
                                              
                if cfg.enforce_multi_tenant_citations:
                    if doc.session_id and doc.session_id != session_id:
                        continue
                    if doc.user_id and doc.user_id != user_id:
                        continue

                valid_chunk_ids.add(doc.chunk_id)
                valid_doc_ids.add(doc.document_id)
                chunk_to_meta[doc.chunk_id] = {
                    "document_id": doc.document_id,
                    "document_filename": doc.document_filename,
                    "page_number": doc.page_number,
                    "section": doc.section,
                    "source_text": doc.source_text,
                }

            for m in context.metrics:
                if m.document_reference:
                    valid_doc_ids.add(m.document_reference)
                metric_chk = f"metric_{m.metric_name}"
                valid_chunk_ids.add(metric_chk)
                chunk_to_meta[metric_chk] = {
                    "document_id": m.document_reference or "metric_store",
                    "document_filename": None,
                    "page_number": m.page_number,
                    "section": "Financial Metrics",
                    "source_text": f"{m.metric_name}: {m.value}",
                }

        for cit in citations:
                                 
            cit_key = f"{cit.chunk_id}::{cit.document_id}::{cit.page_number}"
            if cit_key in seen_keys and cfg.deduplicate_citations:
                duplicate_citations.append(cit.citation_id)
                continue
            seen_keys.add(cit_key)

                                                                              
            if context is None:
                if cit.chunk_id and cit.document_id:
                    valid_citations.append(cit)
                else:
                    cit.is_valid = False
                    cit.validation_error = "Missing chunk_id or document_id"
                    invalid_citations.append(cit)
                continue

                                                      
            is_valid_chunk = cit.chunk_id in valid_chunk_ids
            is_valid_doc = cit.document_id in valid_doc_ids

            if not is_valid_chunk and not is_valid_doc:
                cit.is_valid = False
                cit.validation_error = f"Fabricated or foreign citation reference (chunk='{cit.chunk_id}', doc='{cit.document_id}')."
                invalid_citations.append(cit)
            else:
                                                                                      
                if cit.chunk_id in chunk_to_meta:
                    meta = chunk_to_meta[cit.chunk_id]
                    if cit.document_id and cit.document_id not in ("unknown", meta["document_id"]):
                        cit.is_valid = False
                        cit.validation_error = f"Citation document_id '{cit.document_id}' does not match chunk parent document '{meta['document_id']}'."
                        invalid_citations.append(cit)
                        continue

                    if not cit.document_id or cit.document_id == "unknown":
                        cit.document_id = meta["document_id"]
                    if not cit.document_filename and meta["document_filename"]:
                        cit.document_filename = meta["document_filename"]
                    if cit.page_number is None and meta["page_number"] is not None:
                        cit.page_number = meta["page_number"]
                    if not cit.section and meta["section"]:
                        cit.section = meta["section"]
                    if not cit.quoted_snippet and meta["source_text"]:
                        cit.quoted_snippet = meta["source_text"][:120]

                cit.is_valid = True
                cit.validation_error = None
                valid_citations.append(cit)

        return valid_citations, invalid_citations, duplicate_citations

    def _validate_claims(
        self,
        claims: List[ResearchClaim],
        context: Optional[ResearchContext],
        cfg: OutputValidationConfig,
        valid_citations: Optional[List[ResearchCitation]] = None,
    ) -> Tuple[List[ResearchClaim], List[str]]:
        """Validate, ground, and deduplicate extracted claims."""
        validated_claims: List[ResearchClaim] = []
        duplicate_claims: List[str] = []
        seen_texts: Dict[str, ResearchClaim] = {}

        all_evidence_text = ""
        if context is not None:
            doc_texts = [d.source_text for d in context.documents]
            metric_texts = [f"{m.metric_name} {m.value} {m.period or ''}" for m in context.metrics]
            all_evidence_text = " ".join(doc_texts + metric_texts).lower()

        for claim in claims:
            normalized_text = self._normalize_for_comparison(claim.claim_text)

                                       
            if normalized_text in seen_texts and cfg.deduplicate_claims:
                duplicate_claims.append(claim.claim_text)
                existing = seen_texts[normalized_text]
                                     
                for ref in claim.evidence_refs:
                    if not any(r.chunk_id == ref.chunk_id for r in existing.evidence_refs):
                        existing.evidence_refs.append(ref)
                continue

                                                  
            if context is not None and all_evidence_text:
                extracted_figures = extract_financial_figures(claim.claim_text)
                metric_figures = [f for f in extracted_figures if not f.is_fiscal_year]
                if metric_figures:
                    all_evidence_sources = [d.source_text for d in context.documents] + [
                        f"{m.metric_name} {m.value}" for m in context.metrics
                    ]
                    all_found, supported_figs, unsupported_figs = verify_all_claim_figures_in_evidence(
                        claim.claim_text, all_evidence_sources
                    )
                    if not all_found and unsupported_figs:
                        if supported_figs:
                                                                                           
                            claim.support_status = ClaimSupportStatus.PARTIALLY_SUPPORTED
                            claim.confidence = min(claim.confidence, 0.80)
                            claim.unsupported_reasons.append(
                                f"Derived or ungrounded figure '{unsupported_figs[0].raw_text}' in assertion."
                            )
                        else:
                                                                       
                            claim.support_status = ClaimSupportStatus.UNSUPPORTED
                            claim.confidence = min(claim.confidence, 0.1)
                            claim.unsupported_reasons.append(
                                f"Financial figure '{unsupported_figs[0].raw_text}' not found in verified evidence."
                            )

                if claim.is_causal:
                    causal_in_doc = any(re.search(pat, all_evidence_text, re.IGNORECASE) for pat in CAUSAL_TRIGGERS)
                    if not causal_in_doc:
                        claim.support_status = ClaimSupportStatus.UNSUPPORTED
                        claim.confidence = min(claim.confidence, 0.25)
                        claim.unsupported_reasons.append("Causal relationship lacks explicit supporting evidence.")

            seen_texts[normalized_text] = claim
            validated_claims.append(claim)

        return validated_claims, duplicate_claims

    def _validate_and_calibrate_confidence(
        self,
        resp: ResearchResponse,
        supported_claims: int,
        unsupported_claims: int,
        invalid_citations: int,
        cfg: OutputValidationConfig,
    ) -> Tuple[float, ConfidenceLevel, List[str]]:
        """Validate and calibrate confidence score and confidence level tier."""
        warnings: List[str] = []
        raw_score = resp.confidence

                                                    
        if unsupported_claims > 0:
            if raw_score > cfg.max_confidence_with_unsupported:
                warnings.append(
                    f"Confidence score capped from {raw_score:.2f} to {cfg.max_confidence_with_unsupported:.2f} due to {unsupported_claims} unsupported claim(s)."
                )
                raw_score = min(raw_score, cfg.max_confidence_with_unsupported)

                                                           
        if invalid_citations > 0:
            if raw_score > cfg.max_confidence_with_invalid_citations:
                warnings.append(
                    f"Confidence score capped from {raw_score:.2f} to {cfg.max_confidence_with_invalid_citations:.2f} due to {invalid_citations} invalid citation(s)."
                )
                raw_score = min(raw_score, cfg.max_confidence_with_invalid_citations)

                                                    
        if resp.evidence_conflicts:
            penalty = len(resp.evidence_conflicts) * 0.15
            raw_score = max(0.0, raw_score - penalty)

        final_score = round(max(0.0, min(1.0, raw_score)), 3)

                                                             
        if final_score >= cfg.high_confidence_threshold:
            cal_level = ConfidenceLevel.HIGH
        elif final_score >= cfg.medium_confidence_threshold:
            cal_level = ConfidenceLevel.MEDIUM
        else:
            cal_level = ConfidenceLevel.LOW

        if resp.confidence_level != cal_level:
            warnings.append(
                f"Confidence level tier reconciled from '{resp.confidence_level.value}' to '{cal_level.value}' based on score {final_score:.2f}."
            )

        return final_score, cal_level, warnings

    def _deduplicate_answer_text(self, text: str) -> Tuple[str, int]:
        """Detect and remove repeated verbatim sentence loops in the answer."""
        sentences = re.split(r"(?<=[.!?])\s+", text.strip())
        seen_normalized: Set[str] = set()
        deduped: List[str] = []
        removed_count = 0

        for s in sentences:
            s_clean = s.strip()
            if not s_clean:
                continue
            norm = self._normalize_for_comparison(s_clean)
            if norm in seen_normalized and len(s_clean) > 15:
                removed_count += 1
                continue
            seen_normalized.add(norm)
            deduped.append(s_clean)

        return " ".join(deduped), removed_count

    def _normalize_for_comparison(self, text: str) -> str:
        """Normalize string by removing punctuation, extra spaces, and lowercase."""
        cleaned = text.lower()
        cleaned = cleaned.translate(str.maketrans("", "", string.punctuation))
        return re.sub(r"\s+", " ", cleaned).strip()

    def _is_explicit_negative_finding(self, answer: str, context: Optional[ResearchContext]) -> bool:
        """Distinguish a validated negative finding from missing evidence."""
        negative_indicators = [
            r"\$0\b",
            r"\bzero\b",
            r"\bnone\b",
            r"\bno debt\b",
            r"\bnot incurred\b",
            r"\bno material litigation\b",
            r"\bno outstanding\b",
            r"\bno reported\b",
        ]
        return any(re.search(pat, answer, re.IGNORECASE) for pat in negative_indicators)


                                                                         

output_validation_service = OutputValidationService()
