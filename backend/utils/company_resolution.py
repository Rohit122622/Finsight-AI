"""
FinSentry AI — Canonical Company & Document Resolution Helper.

Resolves natural language entity mentions and ticker symbols to specific session documents
using authoritative document metadata (company_name, ticker, document_id, filename).
Prevents cross-company contamination and guarantees strict document-level isolation.
"""

import re
from typing import Any, Dict, List, Optional, Set, Tuple, Union

# Canonical alias mapping for standard companies in tests and production
CANONICAL_COMPANY_ALIASES: Dict[str, Set[str]] = {
    "apple": {
        "apple", "apple inc", "apple inc.", "apple computer", "aapl", "apple_2025", "apple_2024"
    },
    "bed bath & beyond": {
        "bbby", "bbbyq", "bed bath & beyond", "bed bath & beyond inc", "bed bath and beyond",
        "bed bath & beyond inc.", "bed bath and beyond inc", "bed bath", "bbby_2023", "bbby_2022",
        "bbby_2022_10k", "bbby_distress_10k", "bed bath beyond", "bed bath beyond inc"
    },
    "microsoft": {
        "microsoft", "microsoft corp", "microsoft corp.", "microsoft corporation", "msft"
    },
    "alphabet": {
        "google", "alphabet", "alphabet inc", "alphabet inc.", "goog", "googl"
    },
    "amazon": {
        "amazon", "amazon.com", "amazon com", "amazon.com inc", "amzn"
    },
    "tesla": {
        "tesla", "tesla inc", "tesla inc.", "tesla motors", "tsla"
    },
    "meta": {
        "meta", "meta platforms", "facebook", "meta platforms inc", "fb"
    },
}

# Reverse lookup: alias -> canonical key
ALIAS_TO_CANONICAL: Dict[str, str] = {}
for canonical_key, aliases in CANONICAL_COMPANY_ALIASES.items():
    ALIAS_TO_CANONICAL[canonical_key] = canonical_key
    for alias in aliases:
        ALIAS_TO_CANONICAL[alias.lower()] = canonical_key


CANONICAL_DISPLAY_NAMES: Dict[str, str] = {
    "apple": "Apple",
    "bed bath & beyond": "Bed Bath & Beyond",
    "microsoft": "Microsoft",
    "alphabet": "Alphabet",
    "amazon": "Amazon",
    "tesla": "Tesla",
    "meta": "Meta",
}


def normalize_company_name(name: Optional[str]) -> str:
    """Clean company name for fuzzy matching."""
    if not name or not isinstance(name, str):
        return ""
    cleaned = name.lower().strip()
    cleaned = re.sub(r"[^\w\s\&]", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def get_canonical_company_key(name_or_alias: Optional[str]) -> Optional[str]:
    """Return the canonical key for a company alias or normalized name."""
    if not name_or_alias:
        return None
    normalized = normalize_company_name(name_or_alias)
    if normalized in ALIAS_TO_CANONICAL:
        return ALIAS_TO_CANONICAL[normalized]

    # Check words / sub-phrases
    words = [w for w in normalized.split() if w not in {"inc", "corp", "corporation", "co", "ltd", "llc", "plc", "the", "and", "&"}]
    for word in words:
        if word in ALIAS_TO_CANONICAL:
            return ALIAS_TO_CANONICAL[word]

    # Check if any canonical alias is a substring
    for alias, can_key in ALIAS_TO_CANONICAL.items():
        if len(alias) >= 3 and alias in normalized:
            return can_key

    return normalized if normalized else None


def canonicalize_company_name(name_or_alias: Optional[str]) -> str:
    """Return the standard canonical display name for a company or alias."""
    if not name_or_alias:
        return ""
    key = get_canonical_company_key(name_or_alias)
    if key and key in CANONICAL_DISPLAY_NAMES:
        return CANONICAL_DISPLAY_NAMES[key]
    if key:
        return key.title()
    return str(name_or_alias).strip()


def resolve_company_from_document(doc: Dict[str, Any]) -> str:
    """
    Resolve canonical company name from a document adhering to strict resolution order:
    1. canonical document company metadata (company_name, company)
    2. canonical issuer/ticker metadata (ticker)
    3. validated document/session relationship (document_id)
    4. filename parsing ONLY as a final fallback
    """
    if not isinstance(doc, dict):
        return ""

    # 1. Canonical document company metadata
    c_name = doc.get("company_name") or doc.get("company")
    if c_name and str(c_name).strip():
        canonical = canonicalize_company_name(c_name)
        if canonical:
            return canonical

    # 2. Canonical issuer/ticker metadata
    ticker = doc.get("ticker")
    if ticker and str(ticker).strip():
        canonical = canonicalize_company_name(ticker)
        if canonical:
            return canonical

    # 3. Validated document/session relationship
    doc_id = doc.get("document_id")
    if doc_id and str(doc_id).strip():
        key = get_canonical_company_key(str(doc_id))
        if key and key in CANONICAL_DISPLAY_NAMES:
            return CANONICAL_DISPLAY_NAMES[key]

    # 4. Filename parsing ONLY as a final fallback
    filename = doc.get("filename") or doc.get("document_filename")
    if filename and str(filename).strip():
        canonical = canonicalize_company_name(filename)
        if canonical:
            return canonical

    return "Company"



def is_company_match(target_entity: str, doc: Union[Dict[str, Any], str]) -> bool:
    """
    Check if a target entity string matches a document record or company name string.
    Uses canonical key comparison, document_id, ticker, company_name, and filename.
    """
    if not target_entity or not doc:
        return False

    target_key = get_canonical_company_key(target_entity)
    if not target_key:
        return False

    if isinstance(doc, str):
        doc_key = get_canonical_company_key(doc)
        if doc_key and doc_key == target_key:
            return True
        return target_key in doc.lower() or target_entity.lower() in doc.lower()

    # 1. Compare against document company_name
    doc_company = doc.get("company_name") or doc.get("company") or ""
    if doc_company:
        doc_key = get_canonical_company_key(doc_company)
        if doc_key and doc_key == target_key:
            return True

    # 2. Compare against ticker
    doc_ticker = doc.get("ticker") or ""
    if doc_ticker:
        ticker_key = get_canonical_company_key(doc_ticker)
        if ticker_key and ticker_key == target_key:
            return True

    # 3. Compare against document_id
    doc_id = str(doc.get("document_id") or "").lower()
    if target_key in doc_id:
        return True
    if target_entity.lower() in doc_id:
        return True

    # 4. Fallback: filename
    doc_filename = str(doc.get("filename") or doc.get("document_filename") or "").lower()
    if doc_filename:
        fn_key = get_canonical_company_key(doc_filename)
        if fn_key and fn_key == target_key:
            return True
        if target_key in doc_filename or target_entity.lower() in doc_filename:
            return True

    return False


def resolve_entity_to_document_ids(
    entities: Union[List[str], str],
    documents: List[Dict[str, Any]],
) -> Tuple[List[str], List[str]]:
    """
    Given a list of entity names and available session documents,
    return (resolved_document_ids, matched_company_names).
    """
    if not entities or not documents:
        return [], []

    entity_list = [entities] if isinstance(entities, str) else entities

    matched_doc_ids: Set[str] = set()
    matched_companies: Set[str] = set()

    for ent in entity_list:
        for doc in documents:
            if is_company_match(ent, doc):
                d_id = doc.get("document_id")
                if d_id:
                    matched_doc_ids.add(d_id)
                c_name = doc.get("company_name") or doc.get("filename", "")
                if c_name:
                    matched_companies.add(c_name)

    return sorted(list(matched_doc_ids)), sorted(list(matched_companies))
