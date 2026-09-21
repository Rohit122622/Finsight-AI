"""
FinSentry AI — Deterministic unit tests for the financial-value matcher.

These tests exercise scripts/financial_value_matcher.py in complete isolation:
no MongoDB, no Redis, no LLM, no ResearchAgent, no network. They are pure
function tests and run in milliseconds.

Reference fact under test (official BBBY 2023 10-K):
    fiscal 2022 net sales = 5,344.7 million USD
    fiscal 2021 net sales = 7,871   million USD
"""

import sys
from pathlib import Path

import pytest

# Ensure the backend root is importable regardless of how pytest is invoked
# (mirrors the bootstrap already used by scripts/verify_bbby_research.py).
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from scripts.financial_value_matcher import (
    answer_contains_term,
    financial_value_matches,
    is_numeric_term,
    parse_reference_millions,
)

# Canonical reference terms exactly as used by Q1_FACTUAL.
FY2022 = "5,344.7"   # millions
FY2021 = "7,871"     # millions


# =====================================================================
# 1. Reference parsing (canonical terms are MILLIONS)
# =====================================================================

def test_reference_bare_number_is_millions():
    assert parse_reference_millions(FY2022) == pytest.approx(5344.7)
    assert parse_reference_millions(FY2021) == pytest.approx(7871.0)


def test_reference_accepts_explicit_units():
    assert parse_reference_millions("5.3447 billion") == pytest.approx(5344.7)
    assert parse_reference_millions("5,344.7 million") == pytest.approx(5344.7)


def test_qualitative_term_has_no_numeric_reference():
    for term in ["going concern", "substantial doubt", "risk", "material weakness"]:
        assert parse_reference_millions(term) is None
        assert is_numeric_term(term) is False


def test_numeric_terms_are_detected():
    for term in [FY2022, FY2021, "32.1", "19.8", "31.6", "1,730"]:
        assert is_numeric_term(term) is True


# =====================================================================
# 2. VALID representations of 5,344.7 million — must all match
# =====================================================================

@pytest.mark.parametrize(
    "answer",
    [
        "Net sales were 5,344.7 million in fiscal 2022.",
        "Net sales were 5,344.7M in fiscal 2022.",
        "Net sales were $5,344.7M in fiscal 2022.",
        "Net sales were $5,344.7 million in fiscal 2022.",
        "Net sales were 5.3447 billion in fiscal 2022.",
        "Net sales were $5.3447B in fiscal 2022.",
        "Net sales were 5.345 billion in fiscal 2022.",
        "Net sales were approximately $5.3 billion in fiscal 2022.",
        "Net sales were 5,345 million in fiscal 2022.",
        "Net sales were 5,344,700,000 in fiscal 2022.",
        "Net sales were $5,344,700,000 dollars in fiscal 2022.",
        "Net sales totaled 5,344.7 (in millions) for fiscal 2022.",
    ],
)
def test_valid_representations_match_fy2022(answer):
    assert financial_value_matches(answer, FY2022) is True


@pytest.mark.parametrize(
    "answer",
    [
        "Fiscal 2021 net sales were 7,871 million.",
        "Fiscal 2021 net sales were $7,871M.",
        "Fiscal 2021 net sales were 7.871 billion.",
        "Fiscal 2021 net sales were $7.871B.",
        "Fiscal 2021 net sales were 7,871,000,000.",
    ],
)
def test_valid_representations_match_fy2021(answer):
    assert financial_value_matches(answer, FY2021) is True


def test_single_answer_containing_both_years_matches_both():
    answer = (
        "BBBY reported net sales of $7.871 billion in fiscal 2021 and "
        "$5.3447 billion in fiscal 2022."
    )
    assert financial_value_matches(answer, FY2021) is True
    assert financial_value_matches(answer, FY2022) is True


# =====================================================================
# 3. INVALID values — must NOT match
# =====================================================================

@pytest.mark.parametrize(
    "answer",
    [
        "Net sales were 4.2 billion.",
        "Net sales were 6.1 billion.",
        "Net sales were 5.0 billion.",
        "Net sales were 5.4 billion.",
        "Net sales were 4,200 million.",
        "Net sales were 5,300 million.",
        "Net sales were 5,344,700 dollars.",
        "Net sales were 53.447 billion.",
    ],
)
def test_wrong_values_do_not_match_fy2022(answer):
    assert financial_value_matches(answer, FY2022) is False


def test_fy2021_value_does_not_satisfy_fy2022_reference():
    assert financial_value_matches("Net sales were 7,871 million.", FY2022) is False


def test_percentage_style_values_reject_near_neighbours():
    """A close-but-different figure must fail (guards Q2/Q4 percentage checks)."""
    assert financial_value_matches("Gross margin was 32.1%.", "31.6") is False
    assert financial_value_matches("Net sales fell 31.6%.", "32.1") is False
    # ...while the correct figure still matches.
    assert financial_value_matches("Net sales fell 32.1%.", "32.1") is True
    assert financial_value_matches("Gross margin was 31.6%.", "31.6") is True


# =====================================================================
# 4. Precision-aware tolerance (not a blanket percentage tolerance)
# =====================================================================

def test_tolerance_scales_with_written_precision():
    """
    One-decimal billions imply +/-0.05B rounding, so 5.3B matches 5,344.7M.
    The same absolute error at finer stated precision must NOT be accepted.
    """
    assert financial_value_matches("about $5.3 billion", FY2022) is True
    # 5.30 billion states hundredths precision (+/-5M) -> 44.7M error is too big.
    assert financial_value_matches("about $5.30 billion", FY2022) is False
    # 5,300 million states whole-million precision (+/-0.5M) -> rejected.
    assert financial_value_matches("about 5,300 million", FY2022) is False


def test_exact_precision_rejects_small_but_real_differences():
    """At full stated precision, even a 1-in-53447 difference is wrong."""
    assert financial_value_matches("5,344.7 million", FY2022) is True
    assert financial_value_matches("5,343.7 million", FY2022) is False
    assert financial_value_matches("5,346.0 million", FY2022) is False


def test_rounded_whole_million_is_accepted():
    """5,345M is the correct rounding of 5,344.7M (+/-0.5M band)."""
    assert financial_value_matches("5,345 million", FY2022) is True
    assert financial_value_matches("5,346 million", FY2022) is False


# =====================================================================
# 5. Ordinary prose must not be misread as unit-suffixed finance values
# =====================================================================

@pytest.mark.parametrize(
    "answer",
    [
        "The filing discloses 5 key risk factors.",
        "See Item 5 and Note 5 to the financial statements.",
        "There were 5 material weaknesses identified.",
        "The company operated 955 stores as of fiscal year end.",
    ],
)
def test_prose_digits_are_not_treated_as_magnitudes(answer):
    """A bare '5' followed by a word starting with K/M/B/T is not '5 million'."""
    assert financial_value_matches(answer, FY2022) is False
    # And a bare 5 is 5 million, never 5 billion.
    assert financial_value_matches(answer, "5,000") is False


def test_adjacent_letter_unit_still_parsed():
    """Compact notation remains supported."""
    assert financial_value_matches("Total was 5,344.7M.", FY2022) is True
    assert financial_value_matches("Total was 5.3447B.", FY2022) is True


# =====================================================================
# 6. Qualitative terms keep case-insensitive substring matching
# =====================================================================

@pytest.mark.parametrize(
    "term",
    ["going concern", "substantial doubt", "risk", "material weakness"],
)
def test_qualitative_terms_match_case_insensitively(term):
    answer = (
        "The auditor expressed SUBSTANTIAL DOUBT about the Company's ability to "
        "continue as a Going Concern, citing a Material Weakness and significant Risk."
    )
    assert answer_contains_term(answer, term) is True


def test_qualitative_term_absent_fails():
    answer = "Net sales were 5,344.7 million in fiscal 2022."
    assert answer_contains_term(answer, "going concern") is False


def test_answer_contains_term_dispatches_numeric_vs_qualitative():
    answer = "Net sales were $5.3447B; the auditor noted substantial doubt."
    assert answer_contains_term(answer, FY2022) is True      # numeric path
    assert answer_contains_term(answer, "substantial doubt") is True  # textual path
    assert answer_contains_term(answer, "4.2 billion") is False       # numeric path, wrong


def test_numeric_path_is_not_satisfied_by_keywords_alone():
    """Mentioning 'net sales'/'revenue' must never satisfy a numeric term."""
    answer = "The report discusses net sales, revenue trends and total sales at length."
    assert answer_contains_term(answer, FY2022) is False
    assert answer_contains_term(answer, FY2021) is False
