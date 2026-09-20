"""
FinSentry AI — Research answer formatting fix (BBBY EPS dump bug).

Verifies that _parse_llm_output NEVER surfaces raw document text as the answer,
that a legitimate "unavailable / not reported" answer is preserved, and that a
valid Apple answer (with the EPS value) is preserved unchanged.
"""

import json
from types import SimpleNamespace

from services.evidence_reasoning_service import EvidenceReasoningService, _CONCISE_UNAVAILABLE


def _ctx(doc_texts=None, metrics=None):
    docs = [SimpleNamespace(source_text=t) for t in (doc_texts or [])]
    mets = [SimpleNamespace(metric_name=n, value=v) for (n, v) in (metrics or [])]
    return SimpleNamespace(documents=docs, metrics=mets)


APPLE_DUMP = (
    "APPLE INC. FORM 10-K annual report. " * 200  # large irrelevant filing text
)


def test_placeholder_answer_does_not_dump_raw_document_text():
    svc = EvidenceReasoningService()
    raw = json.dumps({"answer": "Analysis generated from verified session document context."})
    ctx = _ctx(doc_texts=[APPLE_DUMP], metrics=[])
    answer, _kp, _lim, _cit = svc._parse_llm_output(raw, ctx)
    # The huge Apple filing text must NOT appear in the user-facing answer.
    assert "FORM 10-K" not in answer
    assert len(answer) < 200
    assert answer == _CONCISE_UNAVAILABLE


def test_unavailable_answer_is_preserved_not_overwritten():
    svc = EvidenceReasoningService()
    # Legitimate concise "unavailable" answer that happens to contain no digits.
    raw = json.dumps({"answer": "The diluted EPS for Bed Bath & Beyond is not reported in the filing."})
    ctx = _ctx(doc_texts=[APPLE_DUMP], metrics=[])
    answer, _kp, _lim, _cit = svc._parse_llm_output(raw, ctx)
    assert "not reported" in answer.lower()
    assert "FORM 10-K" not in answer  # no dump


def test_apple_answer_with_value_is_preserved():
    svc = EvidenceReasoningService()
    raw = json.dumps({"answer": "Apple's FY2025 diluted EPS was 7.46 and FY2024 was 6.08."})
    ctx = _ctx(doc_texts=[APPLE_DUMP], metrics=[])
    answer, _kp, _lim, _cit = svc._parse_llm_output(raw, ctx)
    assert "7.46" in answer
    assert "6.08" in answer
    assert "FORM 10-K" not in answer


def test_empty_answer_uses_concise_fallback_not_document_dump():
    svc = EvidenceReasoningService()
    ctx = _ctx(doc_texts=[APPLE_DUMP], metrics=[])
    answer, _kp, _lim, _cit = svc._parse_llm_output("", ctx)
    assert "FORM 10-K" not in answer
    assert answer == _CONCISE_UNAVAILABLE
