"""
Deterministic Section Classification Service for FinSentry AI.

Classifies SEC filing sections and financial report components based on
structural patterns, headings, and context without requiring LLM inference.
"""

import logging
import re
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

                                                                 
SECTION_RULE_DEFINITIONS: List[Tuple[re.Pattern, str, str]] = [
                            
    (
        re.compile(r"(?:item\s+1a[\.\:\s\-]+risk\s+factors|risk\s+factors\b)", re.IGNORECASE),
        "risk_factors",
        "Item 1A - Risk Factors",
    ),
                             
    (
        re.compile(r"(?:item\s+1c[\.\:\s\-]+cybersecurity|cybersecurity\s+risk\s+management)", re.IGNORECASE),
        "cybersecurity",
        "Item 1C - Cybersecurity",
    ),
                       
    (
        re.compile(r"(?:item\s+1[\.\:\s\-]+business\b|business\s+overview)", re.IGNORECASE),
        "business",
        "Item 1 - Business",
    ),
                   
    (
        re.compile(
            r"(?:item\s+7[\.\:\s\-]+management['\’]?s\s+discussion|management['\’]?s\s+discussion\s+and\s+analysis)",
            re.IGNORECASE,
        ),
        "md_and_a",
        "Item 7 - MD&A",
    ),
                                        
    (
        re.compile(
            r"(?:item\s+8[\.\:\s\-]+(?:consolidated\s+)?financial\s+statements|consolidated\s+statements?\s+of\s+(?:operations|income|earnings|comprehensive\s+income)|consolidated\s+balance\s+sheets?|consolidated\s+statements?\s+of\s+cash\s+flows?|condensed\s+consolidated\s+financial\s+statements)",
            re.IGNORECASE,
        ),
        "financials",
        "Item 8 - Financial Statements",
    ),
                                                   
    (
        re.compile(
            r"(?:notes?\s+to\s+(?:consolidated\s+)?financial\s+statements?|report\s+of\s+independent\s+registered\s+public\s+accounting\s+firm|auditor['\’]?s\s+report)",
            re.IGNORECASE,
        ),
        "auditor_notes",
        "Notes to Financial Statements & Auditor Report",
    ),
                                
    (
        re.compile(r"(?:item\s+3[\.\:\s\-]+legal\s+proceedings|legal\s+proceedings\b)", re.IGNORECASE),
        "legal",
        "Item 3 - Legal Proceedings",
    ),
                                     
    (
        re.compile(
            r"(?:item\s+10[\.\:\s\-]+directors|item\s+11[\.\:\s\-]+executive\s+compensation|corporate\s+governance)",
            re.IGNORECASE,
        ),
        "governance",
        "Corporate Governance & Directors",
    ),
               
    (
        re.compile(r"(?:footnotes?|see\s+accompanying\s+notes)", re.IGNORECASE),
        "footnotes",
        "Footnotes",
    ),
]


class SectionClassifierService:
    """
    Classifies text chunks and tables into standardized financial sections.
    """

    def classify_text(self, text: str, active_section: Optional[str] = None) -> Tuple[str, str]:
        """
        Classify text chunk into (section_key, section_display_label).
        If a new section header is found, updates and returns the new section.
        Otherwise falls back to the currently active section or 'other'.
        """
        if not text:
            return active_section or "other", active_section or "Other"

                                                              
        for pattern, section_key, display_label in SECTION_RULE_DEFINITIONS:
            if pattern.search(text):
                return section_key, display_label

                                                               
        if active_section:
            return active_section, active_section.replace("_", " ").title()

        return "other", "Other"

    def detect_section_header(self, text: str) -> Optional[Tuple[str, str]]:
        """
        Detect if text contains a top-level section transition header.
        """
        for pattern, section_key, display_label in SECTION_RULE_DEFINITIONS:
            if pattern.search(text):
                return section_key, display_label
        return None


section_classifier_service = SectionClassifierService()
