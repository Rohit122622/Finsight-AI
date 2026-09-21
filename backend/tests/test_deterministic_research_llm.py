"""
FinSentry AI — Deterministic unit tests for the evidence-grounded research stub.

Pure function tests for scripts/deterministic_research_llm.py: no MongoDB, no
Redis, no LLM, no network. They assert the property that makes the BBBY
regression trustworthy -- the stub answers ONLY from the retrieved evidence, so a
retrieval regression still fails the real test.
"""

import json
import sys
from pathlib import Path

import pytest

_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from scripts.deterministic_research_llm import (  # noqa: E402
    deterministic_research_completion,
    extract_evidence_text,
    generate_grounded_answer,
)

# A prompt shaped like backend/prompts/research.py output, using the real fixture
# wording from scripts/generate_bbby_distress_fixture.py.
PROMPT = """<USER_QUESTION>
What were BBBY's net sales in fiscal 2021 and fiscal 2022?
</USER_QUESTION>

<SOURCE_EVIDENCE>
--- RETRIEVED DOCUMENT CHUNKS ---
[CHUNK_1] ID: chk-aaa111 | DocID: doc-bbby | Page: 9 | Score: 0.812
Results of Operations (Page 9): Net sales for fiscal 2022 were $5,345 million, compared to $7,871 million in fiscal 2021, representing a severe top-line decline of $2,526 million or 32.1%.

[CHUNK_2] ID: chk-bbb222 | DocID: doc-bbby | Page: 12 | Score: 0.740
Gross margin compressed precipitously by 11.8 percentage points to 19.8% in fiscal 2022 from 31.6% in fiscal 2021.
</SOURCE_EVIDENCE>
"""


def test_extracts_the_source_evidence_block():
    evidence = extract_evidence_text(PROMPT)
    assert "Net sales for fiscal 2022" in evidence
    assert "19.8%" in evidence


def test_answer_is_grounded_and_contains_the_reported_figures():
    answer = generate_grounded_answer(PROMPT)
    assert "$5,345 million" in answer
    assert "$7,871 million" in answer
    assert "32.1%" in answer


def test_answer_never_leaks_internal_identifiers():
    """The verifier asserts these tokens are absent from user-facing answers."""
    answer = generate_grounded_answer(PROMPT)
    assert "CHUNK_" not in answer
    assert "_chunk_" not in answer
    assert "chk-" not in answer


def test_no_evidence_yields_empty_answer():
    """
    With no retrieved evidence the stub must NOT invent an answer. This is the
    property that keeps the regression honest: it cannot manufacture a pass.
    """
    assert generate_grounded_answer("<USER_QUESTION>anything</USER_QUESTION>") == ""
    empty = "<USER_QUESTION>q</USER_QUESTION>\n<SOURCE_EVIDENCE>\nNo source evidence available.\n</SOURCE_EVIDENCE>"
    assert generate_grounded_answer(empty) == ""


def test_stub_cannot_produce_a_figure_absent_from_evidence():
    """If retrieval loses the net-sales chunk, the figure must not appear."""
    degraded = PROMPT.replace(
        "Results of Operations (Page 9): Net sales for fiscal 2022 were $5,345 million, "
        "compared to $7,871 million in fiscal 2021, representing a severe top-line "
        "decline of $2,526 million or 32.1%.",
        "Item 1. Business. The Company operates retail stores across North America.",
    )
    answer = generate_grounded_answer(degraded)
    assert "5,345" not in answer
    assert "7,871" not in answer


def test_complete_sentence_preferred_over_chunk_truncated_duplicate():
    """
    Chunking can cut a sentence at a boundary. Deduplication must not treat the
    truncated prefix as the complete sentence, or the trailing figure (32.1%)
    would be lost -- this was an observed failure mode.
    """
    prompt = """<USER_QUESTION>
What percentage did net sales decrease from fiscal 2021 to 2022?
</USER_QUESTION>

<SOURCE_EVIDENCE>
--- RETRIEVED DOCUMENT CHUNKS ---
[CHUNK_1] ID: chk-trunc | DocID: doc-bbby | Page: 7 | Score: 0.9
Net sales for fiscal 2022 were $5,345 million, compared to $7,871 million in fiscal

[CHUNK_2] ID: chk-full | DocID: doc-bbby | Page: 9 | Score: 0.8
Net sales for fiscal 2022 were $5,345 million, compared to $7,871 million in fiscal 2021, representing a decline of 32.1%.
</SOURCE_EVIDENCE>
"""
    answer = generate_grounded_answer(prompt)
    assert "32.1%" in answer


def test_numeric_query_tokens_rank_year_bearing_evidence():
    """Fiscal-year tokens must count toward relevance, not be discarded."""
    prompt = """<USER_QUESTION>
What percentage did net sales decrease from fiscal 2021 to 2022?
</USER_QUESTION>

<SOURCE_EVIDENCE>
--- RETRIEVED DOCUMENT CHUNKS ---
[CHUNK_1] ID: chk-1 | DocID: d | Page: 3 | Score: 0.5
The Company maintains distribution centers and leases corporate office space.

[CHUNK_2] ID: chk-2 | DocID: d | Page: 9 | Score: 0.4
2021, representing a severe top-line decline of $2,526 million or 32.1%.
</SOURCE_EVIDENCE>
"""
    assert "32.1%" in generate_grounded_answer(prompt)


def test_completion_returns_research_contract_json():
    raw = deterministic_research_completion(PROMPT)
    data = json.loads(raw)
    assert set(["answer", "key_points", "limitations", "citations"]).issubset(data.keys())
    assert "$5,345 million" in data["answer"]


def test_completion_is_deterministic_across_calls():
    """Identical prompt -> byte-identical output (the whole point of the stub)."""
    first = deterministic_research_completion(PROMPT)
    for _ in range(5):
        assert deterministic_research_completion(PROMPT) == first
