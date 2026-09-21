"""
FinSentry AI — Financial-value matcher for real-world research verification.

Test-support/validation code only. Pure standard library (re): it does NOT
import the ResearchAgent, MongoDB, or any LLM, so it can be unit-tested
deterministically in isolation.

Purpose
-------
Real-world research answers state the same underlying financial fact in many
valid ways. For BBBY fiscal-2022 net sales (official reference: 5,344.7 million
USD) an answer may legitimately say any of:

    "5,344.7 million"      "$5,344.7M"        "5,345 million"
    "5.3447 billion"       "$5.3447B"         "5.345 billion"
    "approximately $5.3 billion"              "5,344,700,000"

All of these represent the same value once normalized to a common unit
(millions). A brittle substring check on one exact string is therefore wrong.

Approach
--------
1. Parse numeric financial expressions, capturing an optional currency symbol,
   thousands separators, decimals, and a magnitude unit
   (thousand/million/billion/trillion or K/M/B/T).
2. Normalize every parsed value to MILLIONS.
3. Compare using a PRECISION-AWARE tolerance: a stated figure represents any
   true value that would round to it at the stated precision. The tolerance is
   half of one unit in the last significant digit of the representation, e.g.

       "5,344.7 million" -> band +/- 0.05 million   (near exact)
       "5,345 million"   -> band +/- 0.5 million    (rounded whole million)
       "5.345 billion"   -> band +/- 0.5 million    (0.001 billion)
       "5.3447 billion"  -> band +/- 0.05 million
       "5.3 billion"     -> band +/- 50 million     (0.1 billion)

   So "5.3 billion" accepts 5,344.7 (|5300 - 5344.7| = 44.7 <= 50) but
   "4.2 billion" (band [4150, 4250]) and "5.4 billion" (band [5350, 5450])
   both correctly reject it.

Bare numbers (no magnitude unit) follow the research-answer convention: they are
interpreted as MILLIONS (matching the canonical reference terms "5,344.7" and
"7,871"). A bare number is ALSO given a raw-dollars interpretation ONLY when it
is a large full-dollar integer (>= 1,000,000, no decimal point) — e.g.
"5,344,700,000" -> 5,344.7 million. This is deliberately narrow: it never adds a
dollar interpretation to ordinary figures like "32.1" or "5,344.7", so it cannot
let an obviously wrong value pass. (The millions and dollars interpretations of a
qualifying integer are 10^6 apart, so only the genuinely-correct full-dollar
figure can match.)
"""

import re

# Magnitude unit -> multiplier that converts a value expressed in that unit
# into MILLIONS of dollars. (A "billion" is 1_000 millions, etc.)
_UNIT_TO_MILLIONS = {
    "thousand": 1e-3,
    "million": 1.0,
    "billion": 1e3,
    "trillion": 1e6,
    "k": 1e-3,
    "m": 1.0,
    "b": 1e3,
    "t": 1e6,
}

# A number: optional currency symbol, digits with optional thousands separators,
# optional decimal part, then an OPTIONAL magnitude unit. Full-word units may be
# separated by whitespace; single-letter units (K/M/B/T) must be adjacent to the
# number (standard compact notation like "5.3B", "$5,344.7M") so we don't misread
# prose such as "5 key risks".
# NOTE on the `num` alternation order: the comma-grouped form requires at least one
# comma group (`+`, not `*`). With `*` the first alternative would match only the
# leading 1-3 digits of a comma-less integer -- "5344700000" parsed as "534" -- so
# plain digit runs must fall through to the second alternative, which is greedy.
_NUMBER_PATTERN = re.compile(
    r"\$?\s*"
    r"(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"(?:\s*(?P<word>thousand|million|billion|trillion)\b|(?P<letter>[KMBT])\b)?",
    re.IGNORECASE,
)

# Guard against floating-point representation error at the band edge.
_EPSILON = 1e-9


def _decimals(num_text: str) -> int:
    """Number of digits after the decimal point in the written number (commas removed)."""
    cleaned = num_text.replace(",", "")
    if "." in cleaned:
        return len(cleaned.split(".", 1)[1])
    return 0


# A bare number is additionally treated as a full-dollar amount only when it is
# an integer of at least this magnitude (e.g. "5,344,700,000").
_FULL_DOLLAR_MIN = 1_000_000


def parse_financial_candidates(text):
    """
    Find every financial figure in *text* and return a list of
    (value_in_millions, half_ulp_in_millions) tuples.

    Interpretation rules:
      * An explicit magnitude unit controls the interpretation outright.
      * A bare number is MILLIONS by convention (matches the canonical
        reference terms used by this suite).
      * A bare number additionally gets a full-dollar interpretation ONLY when
        it is an integer >= 1,000,000 with no decimal point — e.g.
        "5,344,700,000" -> 5,344.7 million. Ordinary figures such as "32.1" or
        "5,344.7" never receive a dollar interpretation.
    """
    candidates = []
    for match in _NUMBER_PATTERN.finditer(text):
        num_text = match.group("num")
        try:
            num = float(num_text.replace(",", ""))
        except ValueError:
            continue

        decimals = _decimals(num_text)
        half_ulp_units = 0.5 * (10.0 ** (-decimals))  # in the number's own unit

        unit = match.group("word") or match.group("letter")
        if unit:
            mult = _UNIT_TO_MILLIONS[unit.lower()]
            candidates.append((num * mult, half_ulp_units * mult))
            continue

        # Bare number: canonical millions.
        candidates.append((num, half_ulp_units))

        # Narrow extra case: large full-dollar integer -> convert to millions.
        if decimals == 0 and num >= _FULL_DOLLAR_MIN:
            candidates.append((num * 1e-6, half_ulp_units * 1e-6))

    return candidates


def parse_reference_millions(term):
    """
    Parse a canonical expected term (e.g. "5,344.7", "7,871", "5.3447 billion")
    into a float in MILLIONS, or return None if the term has no numeric content
    (i.e. it is a qualitative term like "going concern").

    A bare reference is treated as already being in millions, matching the
    convention used for the official reference values.
    """
    match = _NUMBER_PATTERN.search(term)
    if not match:
        return None
    try:
        num = float(match.group("num").replace(",", ""))
    except (ValueError, TypeError):
        return None
    unit = match.group("word") or match.group("letter")
    mult = _UNIT_TO_MILLIONS[unit.lower()] if unit else 1.0
    return num * mult


def is_numeric_term(term):
    """True if *term* is a numeric/financial expected term (else it is qualitative)."""
    return parse_reference_millions(term) is not None


def financial_value_matches(answer, term):
    """
    Return True if *answer* contains a financial figure that represents the
    reference value in *term*, using precision-aware rounding tolerance.
    """
    reference_mm = parse_reference_millions(term)
    if reference_mm is None:
        raise ValueError(f"{term!r} is not a numeric financial term")

    for value_mm, half_ulp_mm in parse_financial_candidates(answer):
        if abs(value_mm - reference_mm) <= half_ulp_mm + _EPSILON:
            return True
    return False


def answer_contains_term(answer, term):
    """
    Validate that an expected term is present in a research answer.

    Numeric/financial terms are validated by NORMALIZED VALUE with precision-aware
    tolerance (see financial_value_matches). Qualitative terms (e.g. "going
    concern", "substantial doubt", "risk") fall back to case-insensitive
    substring matching.
    """
    if is_numeric_term(term):
        return financial_value_matches(answer, term)
    return term.lower() in answer.lower()
