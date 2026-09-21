"""
FinSentry AI — Deterministic, evidence-grounded generation stub for the
real-world research regression tests.

Test-support code only. Pure standard library (json, re). It does NOT import the
ResearchAgent, MongoDB, or any LLM provider, so it is unit-testable in isolation.

WHY THIS EXISTS
---------------
`scripts/verify_bbby_research.py` asserts that the research answer states the
filing's real figures (e.g. fiscal-2022 net sales). Answer *composition* is the
only non-deterministic step in that pipeline:

  * Locally, LLM provider keys are present, a live model composes the answer, and
    the figures appear (in some valid format).
  * In GitHub Actions no provider keys exist, so every provider in
    `LLMFallbackService` fails with AUTH_ERROR ("Missing API key credentials"),
    the chain exhausts, and the offline rules engine returns a generic JSON whose
    `executive_summary` placeholder is then replaced by
    `evidence_reasoning_service._parse_llm_output` with the constant
    "The requested value is not reported in the uploaded filing."
    That answer contains no figures at all, so the expected-term assertion can
    never pass in CI regardless of how tolerant the numeric matcher is.

This module removes that non-determinism WITHOUT weakening the test: it replaces
only the LLM generation seam with a deterministic extractive summarizer that
reads the retrieved evidence out of the composed prompt and answers from it.

WHAT REMAINS GENUINELY UNDER TEST
---------------------------------
Everything except model wording: PDF ingestion, chunking, embedding, hybrid
retrieval, query understanding, pre-retrieval refusal gates, claim extraction and
grounding verification, citation validation against real chunk IDs/pages, MongoDB
persistence and session memory.

Critically, this stub NEVER hardcodes an expected value. Every figure it emits is
copied verbatim from the `<SOURCE_EVIDENCE>` block of the real prompt. If
retrieval regressed and the net-sales evidence stopped being retrieved, the stub
would emit no such figure and the regression assertion would correctly FAIL.
"""

import json
import re

# Chunk blocks in the composed research prompt look like:
#   [CHUNK_1] ID: chk-... | DocID: ... | Page: 7 | Score: 0.812
#   <chunk text>
# (see backend/prompts/research.py::_build_source_evidence)
_EVIDENCE_BLOCK_RE = re.compile(r"<SOURCE_EVIDENCE>(.*?)</SOURCE_EVIDENCE>", re.DOTALL)
_CHUNK_HEADER_RE = re.compile(r"^\[CHUNK_\d+\]\s*ID:.*$", re.MULTILINE)
_METRIC_LINE_RE = re.compile(r"^-\s*[A-Z0-9_]+:.*$", re.MULTILINE)

# Tokens that must never reach a user-facing answer (asserted by the verifier).
_FORBIDDEN_TOKEN_RE = re.compile(r"(CHUNK_|_chunk_|chk-)", re.IGNORECASE)

# Stopwords ignored when scoring evidence sentences against the question.
_STOPWORDS = {
    "what", "were", "was", "the", "in", "and", "of", "a", "an", "is", "are",
    "for", "to", "did", "do", "does", "how", "much", "many", "that", "this",
    "they", "their", "it", "its", "from", "by", "on", "at", "with", "about",
    "tell", "me", "compare", "between", "percentage", "same", "period",
}


def extract_evidence_text(prompt: str) -> str:
    """Return the raw text inside <SOURCE_EVIDENCE>, or "" if absent."""
    match = _EVIDENCE_BLOCK_RE.search(prompt)
    return match.group(1) if match else ""


def _evidence_sentences(prompt: str):
    """
    Split the retrieved evidence into candidate sentences, with chunk-ID header
    lines and canonical-metric lines stripped out (headers carry internal IDs).
    """
    evidence = extract_evidence_text(prompt)
    if not evidence:
        return []

    evidence = _CHUNK_HEADER_RE.sub(" ", evidence)
    evidence = _METRIC_LINE_RE.sub(" ", evidence)

    # Drop structural separators such as "--- RETRIEVED DOCUMENT CHUNKS ---".
    evidence = re.sub(r"-{2,}[^\n]*-{2,}", " ", evidence)

    sentences = []
    for raw in re.split(r"(?<=[.!?])\s+|\n+", evidence):
        s = " ".join(raw.split())
        if len(s) < 25:
            continue
        if _FORBIDDEN_TOKEN_RE.search(s):
            continue
        sentences.append(s)
    return sentences


def _question(prompt: str) -> str:
    match = re.search(r"<USER_QUESTION>(.*?)</USER_QUESTION>", prompt, re.DOTALL)
    return match.group(1) if match else prompt


def _keywords(question: str):
    """
    Query tokens used to rank evidence. Numeric tokens are included on purpose:
    fiscal years and figures ("2021", "2022") are among the most discriminating
    terms in financial questions.
    """
    words = re.findall(r"[a-z0-9]{3,}", question.lower())
    return {w for w in words if w not in _STOPWORDS}


def _score(sentence: str, keywords) -> float:
    """Rank an evidence sentence by keyword overlap, with a bonus for figures."""
    lower = sentence.lower()
    hits = sum(1 for kw in keywords if kw in lower)
    score = float(hits)
    # Prefer sentences that actually state numbers/percentages — factual queries
    # in this suite are about reported figures.
    if re.search(r"\$\s?[\d,]+(?:\.\d+)?|\b\d+(?:\.\d+)?\s?%", sentence):
        score += 1.5
    return score


def generate_grounded_answer(prompt: str, max_sentences: int = 24) -> str:
    """
    Build an extractive answer from the retrieved evidence in *prompt*.

    Selects the evidence sentences most relevant to the question, preserving the
    filing's own wording and figures verbatim. Returns "" when the prompt carries
    no usable evidence (the caller then behaves as the normal no-answer path).
    """
    sentences = _evidence_sentences(prompt)
    if not sentences:
        return ""

    keywords = _keywords(_question(prompt))

    scored = []
    for idx, sentence in enumerate(sentences):
        scored.append((_score(sentence, keywords), -idx, sentence))
    scored.sort(reverse=True)

    selected = []
    seen = set()
    for score, _neg_idx, sentence in scored:
        if score <= 0:
            continue
        # Collapse exact duplicates. The fixture intentionally repeats MD&A text
        # across pages, so the same sentence is retrieved several times. Compare the
        # FULL normalized form (never a prefix) so that a sentence truncated at a
        # chunk boundary is not mistaken for the complete sentence — the complete
        # one carries figures the truncated one lost.
        fingerprint = re.sub(r"\(page \d+\)", "", sentence.lower())
        fingerprint = re.sub(r"[^a-z0-9]+", "", fingerprint)
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        selected.append(sentence)
        if len(selected) >= max_sentences:
            break

    return " ".join(selected)


def deterministic_research_completion(prompt: str, system_prompt=None) -> str:
    """
    Deterministic stand-in for a research LLM completion.

    Returns a JSON object shaped like the research response contract so that
    `evidence_reasoning_service._parse_llm_output` consumes it through its normal
    JSON branch. The `answer` is extracted verbatim from the prompt's
    `<SOURCE_EVIDENCE>`, never fabricated.
    """
    answer = generate_grounded_answer(prompt)
    payload = {
        "answer": answer,
        "key_points": [],
        "limitations": [],
        "citations": [],
    }
    return json.dumps(payload, indent=2)
