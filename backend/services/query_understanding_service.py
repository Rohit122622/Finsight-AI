"""
FinSentry AI — Phase 3B Query Understanding Service.

Implements deterministic query understanding for financial research:
  1. Query normalization (clean punctuation/whitespace while strictly preserving numbers/currencies/years)
  2. Financial and temporal signal extraction
  3. Query classification (FACTUAL, FINANCIAL_METRIC, COMPARISON, TREND, CAUSAL, RISK, etc.)
  4. Multi-step query detection
  5. Follow-up and conversation context detection
  6. Query expansion and reformulation (domain synonyms without hallucinating facts)
  7. Generation of structured QueryUnderstandingResult for Phase 3A Retrieval
"""

import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from schemas.query_understanding import (
    FinancialSignal,
    QueryClassification,
    QueryContextType,
    QueryUnderstandingRequest,
    QueryUnderstandingResult,
    TemporalSignal,
)

logger = logging.getLogger(__name__)


                                                                       

                                                                 
COMMON_FINANCIAL_STOPWORDS: Set[str] = {
    "what", "how", "why", "when", "where", "which", "who", "whom", "whose",
    "is", "was", "are", "were", "be", "been", "being", "have", "has", "had",
    "do", "does", "did", "can", "could", "should", "would", "will", "shall",
    "the", "a", "an", "this", "that", "these", "those", "my", "our", "your", "their", "its",
    "them", "they", "we", "us", "you", "i", "me", "him", "her", "both", "all", "either", "neither",
    "in", "on", "at", "for", "from", "to", "by", "with", "about", "against", "between", "into", "through", "during", "before", "after", "above", "below", "under",
    "much", "many", "far", "long", "often", "such", "so", "some", "any", "no", "not", "only", "same",
    "revenue", "sales", "net", "gross", "income", "profit", "loss", "margin", "ebitda", "ebit", "opex", "capex",
    "debt", "equity", "cash", "flow", "assets", "liabilities", "balance", "sheet", "statement", "operations",
    "fiscal", "year", "quarter", "fy", "q1", "q2", "q3", "q4", "annual", "report", "filing", "10-k", "10-q", "sec",
    "form", "notes", "financial", "statements", "covenant", "ratio", "guidance", "risk", "factors",
    "growth", "change", "increase", "decrease", "trend", "performance", "metric", "metrics", "number", "numbers",
    "compare", "comparing", "comparison", "versus", "vs", "difference", "summary", "overview", "total", "average",
    "higher", "lower", "better", "worse", "greater", "less", "more", "most", "least", "rates", "rate",
    "diluted", "basic", "eps", "shares", "share", "stock", "price", "valuation", "market", "cap", "capitalization",
    "dividend", "dividends", "payout", "leverage", "liquidity", "segment", "segments", "product", "products",
    "services", "geographic", "region", "audit", "auditor", "auditors", "opinion", "material", "weakness", "accounting",
    "independent", "management", "board", "directors", "committee", "officer", "officers", "executive", "executives",
    "usd", "eur", "gbp", "million", "billion", "trillion", "thousand", "dollars", "percent", "percentage", "bps",
    "company", "companies", "firm", "firms", "business", "businesses", "corporation", "corporate",
    "show", "tell", "give", "find", "get", "calculate", "analyze", "explain", "describe", "provide", "state", "list", "check", "highlight",
    "disclose", "disclosed", "disclosing", "disclosure", "disclosures", "reported", "reporting", "stated", "stating",
    "mentioned", "discussed", "given", "indicated", "included", "per", "according", "shown", "biggest", "largest", "smallest", "main", "key", "primary",
}

                                             
FINANCIAL_METRIC_MAP: Dict[str, List[str]] = {
    "revenue": ["revenue", "gross revenue", "net revenue", "top line", "sales", "net sales", "total revenue", "turnover"],
    "net_income": ["net income", "profit", "net profit", "bottom line", "net earnings", "earnings after tax", "net loss"],
    "ebitda": ["ebitda", "adjusted ebitda", "operating profit before depreciation", "operating cash flow"],
    "ebit": ["ebit", "operating income", "operating profit", "operating earnings"],
    "gross_margin": ["gross margin", "gross profit margin", "gross profit"],
    "operating_margin": ["operating margin", "operating profit margin", "operating income margin"],
    "profit_margin": ["profit margin", "net margin", "net profit margin"],
    "operating_expenses": ["operating expenses", "opex", "sg&a", "selling general and administrative", "overhead"],
    "capex": ["capex", "capital expenditures", "capital spending", "additions to property"],
    "r_and_d": ["r&d", "research and development", "r and d", "research & development"],
    "cash": ["cash", "cash and cash equivalents", "cash balance", "cash reserves", "liquidity"],
    "cash_flow": ["cash flow", "free cash flow", "operating cash flow", "fcf", "cash from operations"],
    "debt": ["debt", "total debt", "long-term debt", "short-term debt", "borrowings", "leverage", "liabilities"],
    "debt_to_equity": ["debt-to-equity", "debt to equity", "d/e ratio"],
    "eps": ["eps", "earnings per share", "diluted eps", "basic eps"],
    "assets": ["assets", "total assets", "current assets", "non-current assets"],
    "liabilities": ["liabilities", "total liabilities", "current liabilities"],
    "equity": ["equity", "shareholders equity", "stockholders equity", "book value", "net worth"],
    "market_cap": ["market cap", "market capitalization", "valuation"],
    "dividends": ["dividend", "dividends", "dividend yield", "payout ratio"],
    "guidance": ["guidance", "financial outlook", "forecast", "forward-looking guidance"],
}

                                          
METRIC_TERM_TO_CANONICAL: Dict[str, str] = {}
for canonical, synonyms in FINANCIAL_METRIC_MAP.items():
    for syn in synonyms:
        METRIC_TERM_TO_CANONICAL[syn.lower()] = canonical

                                     
METRIC_TO_SECTION_HINT: Dict[str, str] = {
    "revenue": "revenue",
    "gross_margin": "revenue",
    "net_income": "income",
    "ebitda": "income",
    "ebit": "income",
    "operating_margin": "income",
    "profit_margin": "income",
    "operating_expenses": "expenses",
    "capex": "cash_flow",
    "r_and_d": "expenses",
    "cash": "balance_sheet",
    "cash_flow": "cash_flow",
    "debt": "balance_sheet",
    "debt_to_equity": "balance_sheet",
    "eps": "income",
    "assets": "balance_sheet",
    "liabilities": "balance_sheet",
    "equity": "balance_sheet",
    "market_cap": "valuation",
    "dividends": "cash_flow",
    "guidance": "guidance",
}

                                                                            
QUERY_EXPANSION_DICTIONARY: Dict[str, List[str]] = {
    "top line": ["revenue", "total revenue", "net sales"],
    "bottom line": ["net income", "net profit", "earnings"],
    "operating income": ["operating profit", "EBIT", "operating earnings"],
    "ebitda": ["operating profit before depreciation", "adjusted EBITDA"],
    "risk": ["risk factors", "material risks", "business risks", "uncertainties"],
    "risks": ["risk factors", "material risks", "business risks", "disclosed risk factors"],
    "risk factors": ["material risks", "business risks", "risk disclosures"],
    "capex": ["capital expenditures", "property and equipment additions"],
    "opex": ["operating expenses", "SG&A expenses"],
    "cash flow": ["free cash flow", "cash flows from operating activities"],
    "debt": ["total debt", "long-term obligations", "borrowings"],
    "liquidity": ["cash reserves", "cash and cash equivalents", "liquidity position"],
    "rd": ["research and development", "R&D investments"],
    "r&d": ["research and development", "R&D investments"],
}

                               
COMPARISON_KEYWORDS = [
    "compare", "comparing", "comparison", "versus", "vs", "vs.",
    "difference between", "differ from", "higher than", "lower than",
    "greater than", "less than", "relative to", "compared to",
    "better than", "worse than", "outperform", "underperform",
    "increase over", "decrease from", "change from", "change between"
]

                
TREND_KEYWORDS = [
    "trend", "trends", "historical", "trajectory", "evolution",
    "growth rate", "grew by", "declined by", "changed from",
    "over time", "year over year", "quarter over quarter",
    "yoy", "qoq", "y-o-y", "q-o-q", "compound", "cagr",
    "increased from", "decreased from", "rose from", "fell from",
    "consistently", "momentum", "progression"
]

                 
CAUSAL_KEYWORDS = [
    "why did", "why has", "why is", "what caused", "what drove",
    "drivers of", "driver behind", "reasons for", "reason behind",
    "due to", "because of", "explain why", "factor behind",
    "catalyst for", "account for the", "contributed to", "impact of"
]

               
RISK_KEYWORDS = [
    "risk", "risks", "risk factors", "threat", "threats",
    "headwind", "headwinds", "vulnerability", "vulnerabilities",
    "uncertainty", "uncertainties", "challenges", "downside",
    "exposure", "material risk", "adverse effect"
]

                     
DEFINITION_KEYWORDS = [
    "what is", "what are", "define", "definition of", "meaning of",
    "what does", "explain what", "how is defined"
]

                  
SUMMARY_KEYWORDS = [
    "summarize", "summary", "overview", "brief overview",
    "key takeaways", "executive summary", "highlight", "highlights",
    "main points", "synthesize", "recap"
]

                          
DOCUMENT_LOOKUP_KEYWORDS = [
    "where in the document", "which section", "what page",
    "find the page", "table of contents", "exhibit", "footnote",
    "in the 10-k", "in the 10-q", "in the annual report", "located in"
]

                                                     
FOLLOW_UP_PRONOUNS = [
    "it", "its", "they", "them", "their", "that", "this", "these", "those",
    "the company's", "the same", "that period", "that year"
]

FOLLOW_UP_PATTERNS = [
    r"^(?:how|what)\s+about\b",
    r"^(?:why|how)\s+did\s+(?:it|they|that|this)\b",
    r"^(?:and|what\s+about)\s+(?:in|for)?\s*(?:fy)?\s*\d{2,4}\b",
    r"^why\?*$",
    r"^compare\s+(?:that|it|this)\b",
    r"^same\s+for\b",
    r"^what\s+else\b",
    r"^explain\s+(?:that|this|it)\b",
    r"^how\s+much\s+(?:did\s+it|was\s+it)\b",
    r"^did\s+it\s+(?:increase|decrease|grow|decline)\b",
]


class QueryUnderstandingService:
    """
    Service for parsing, normalizing, classifying, and structuring
    user financial queries before Phase 3A retrieval.
    """

                                                                       

    def understand_query(
        self,
        request: QueryUnderstandingRequest,
    ) -> QueryUnderstandingResult:
        """
        Analyze the user's natural language question and produce a structured
        QueryUnderstandingResult contract.

        Args:
            request: Validated request with query string and optional conversation history.

        Returns:
            QueryUnderstandingResult with complete classification, signals, and expansion.
        """
        raw_query = request.query.strip()
        if not raw_query:
            raise ValueError("Query string cannot be empty")

                                
        normalized = self.normalize_query(raw_query)

                            
        financial_signals = self.extract_financial_signals(normalized)
        temporal_signals = self.extract_temporal_signals(normalized)

                              
        is_multi_step = self.detect_multi_step(normalized, financial_signals, temporal_signals)

                                                  
        is_follow_up, requires_context, context_type = self.detect_follow_up_and_context(
            normalized, request.conversation_history
        )

        # Multi-turn Context & Metric Inheritance:
        # If this is a follow-up turn lacking explicit financial metrics or entity,
        # inherit them from the previous conversation turns in history.
        if (is_follow_up or requires_context) and request.conversation_history:
            if not financial_signals.metrics:
                for turn in reversed(request.conversation_history[-4:]):
                    prev_content = turn.get("content", "")
                    prev_fin = self.extract_financial_signals(self.normalize_query(prev_content))
                    if prev_fin.metrics:
                        financial_signals = FinancialSignal(
                            metrics=prev_fin.metrics,
                            currencies=financial_signals.currencies or prev_fin.currencies,
                            percentages=financial_signals.percentages or prev_fin.percentages,
                            comparison_indicators=financial_signals.comparison_indicators or prev_fin.comparison_indicators,
                            raw_values=financial_signals.raw_values or prev_fin.raw_values,
                        )
                        break

            # If follow-up lacks temporal signals, inherit previous periods from history
            if not temporal_signals.years:
                for turn in reversed(request.conversation_history[-4:]):
                    prev_content = turn.get("content", "")
                    prev_temp = self.extract_temporal_signals(self.normalize_query(prev_content))
                    if prev_temp.years:
                        temporal_signals = TemporalSignal(
                            years=prev_temp.years,
                            fiscal_years=temporal_signals.fiscal_years or prev_temp.fiscal_years,
                            quarters=temporal_signals.quarters or prev_temp.quarters,
                            date_ranges=temporal_signals.date_ranges or prev_temp.date_ranges,
                            raw_temporal_terms=temporal_signals.raw_temporal_terms or prev_temp.raw_temporal_terms,
                        )
                        break

                            
        classification, secondary = self.classify_query(
            normalized,
            financial_signals=financial_signals,
            temporal_signals=temporal_signals,
            is_multi_step=is_multi_step,
            is_follow_up=is_follow_up,
        )

        # Phase 3B Entity Extraction
        entities = self.extract_entities(raw_query, normalized, request.conversation_history)

        # Query Expansion using domain synonyms, inherited metrics, and temporal context
        expanded_queries = self.expand_query(
            normalized,
            financial_signals=financial_signals,
            temporal_signals=temporal_signals,
            entities=entities,
        )

        # Multi-part query decomposition into focused sub-queries
        sub_queries = self.decompose_query(
            normalized_query=normalized,
            financial_signals=financial_signals,
            temporal_signals=temporal_signals,
            is_multi_step=is_multi_step,
            entities=entities,
        )
        if sub_queries and not is_multi_step:
            is_multi_step = True

                                     
        retrieval_hints = self._generate_retrieval_hints(
            classification, financial_signals, temporal_signals
        )
        if entities:
            retrieval_hints["entities"] = entities

        result = QueryUnderstandingResult(
            original_query=raw_query,
            normalized_query=normalized,
            classification=classification,
            secondary_classifications=secondary,
            is_multi_step=is_multi_step,
            is_follow_up=is_follow_up,
            requires_context=requires_context,
            context_type=context_type,
            expanded_queries=expanded_queries,
            sub_queries=sub_queries,
            financial_signals=financial_signals,
            temporal_signals=temporal_signals,
            entities=entities,
            retrieval_hints=retrieval_hints,
        )

        logger.info(
            "Query understood: class=%s (multi_step=%s, follow_up=%s, entities=%s, signals=%d metrics, %d years)",
            result.classification.value,
            result.is_multi_step,
            result.is_follow_up,
            result.entities,
            len(result.financial_signals.metrics),
            len(result.temporal_signals.years),
        )

        return result

                                                                       

    def normalize_query(self, query: str) -> str:
        """
        Normalize query string without destroying financial numbers, years,
        percentages, currency symbols, or domain entities.
        """
        if not query:
            return ""

        text = query.strip()

                                                                                     
        text = re.sub(r'\?{2,}', '?', text)
        text = re.sub(r'!{2,}', '!', text)
        text = re.sub(r'\.{3,}', '...', text)
        text = re.sub(r'\.{2}', '.', text)

                                                                                                     
        text = re.sub(r'\s+', ' ', text)

                                                                               
        text = re.sub(r'\bFY\s+(\d{2,4})\b', r'FY\1', text, flags=re.IGNORECASE)
        text = re.sub(r'\bFiscal\s+Year\s+(\d{2,4})\b', r'FY\1', text, flags=re.IGNORECASE)

                                                                       
        text = re.sub(r'\bQ\s+([1-4])\b', r'Q\1', text, flags=re.IGNORECASE)
        text = re.sub(r'\b1st\s+quarter\b', 'Q1', text, flags=re.IGNORECASE)
        text = re.sub(r'\b2nd\s+quarter\b', 'Q2', text, flags=re.IGNORECASE)
        text = re.sub(r'\b3rd\s+quarter\b', 'Q3', text, flags=re.IGNORECASE)
        text = re.sub(r'\b4th\s+quarter\b', 'Q4', text, flags=re.IGNORECASE)

                                 
        text = re.sub(r'\by-o-y\b', 'YoY', text, flags=re.IGNORECASE)
        text = re.sub(r'\bq-o-q\b', 'QoQ', text, flags=re.IGNORECASE)

        return text.strip()

                                                                       

    def extract_financial_signals(self, text: str) -> FinancialSignal:
        """
        Extract financial metrics, currency figures, percentages, and comparison signals.
        """
        text_lower = text.lower()
        metrics: Set[str] = set()
        currencies: List[str] = []
        percentages: List[str] = []
        comp_indicators: List[str] = []
        raw_values: List[str] = []

                                       
                                                                          
        sorted_phrases = sorted(METRIC_TERM_TO_CANONICAL.keys(), key=len, reverse=True)
        for phrase in sorted_phrases:
            pattern = r'\b' + re.escape(phrase) + r'\b'
            if re.search(pattern, text_lower):
                canonical = METRIC_TERM_TO_CANONICAL[phrase]
                metrics.add(canonical)

                                                                               
        currency_patterns = [
            r'[\$€£¥]\s*[\d,]+(?:\.\d+)?(?:\s*(?:billion|million|trillion|bn|mn|m|b|k))?',
            r'[\d,]+(?:\.\d+)?\s*(?:billion|million|trillion)\s*(?:dollars|usd|eur|gbp)?',
            r'[\d,]+(?:\.\d+)?\s*(?:dollars|usd|eur|gbp)',
        ]
        for pat in currency_patterns:
            for match in re.finditer(pat, text, flags=re.IGNORECASE):
                val = match.group(0).strip()
                if val and val not in currencies:
                    currencies.append(val)
                    raw_values.append(val)

                                               
        percentage_patterns = [
            r'[\d,]+(?:\.\d+)?\s*%',
            r'[\d,]+(?:\.\d+)?\s*(?:percent|percentage)',
            r'[\d,]+(?:\.\d+)?\s*(?:basis\s+points|bps)',
        ]
        for pat in percentage_patterns:
            for match in re.finditer(pat, text, flags=re.IGNORECASE):
                val = match.group(0).strip()
                if val and val not in percentages:
                    percentages.append(val)
                    raw_values.append(val)

                                          
        for kw in COMPARISON_KEYWORDS:
            pattern = r'\b' + re.escape(kw) + r'\b'
            if re.search(pattern, text_lower):
                if kw not in comp_indicators:
                    comp_indicators.append(kw)

        return FinancialSignal(
            metrics=sorted(list(metrics)),
            currencies=currencies,
            percentages=percentages,
            comparison_indicators=comp_indicators,
            raw_values=raw_values,
        )

                                                                       

    def extract_temporal_signals(self, text: str) -> TemporalSignal:
        """
        Extract years, fiscal years, quarters, and date ranges.
        """
        years: Set[int] = set()
        fiscal_years: List[str] = []
        quarters: List[str] = []
        date_ranges: List[str] = []
        raw_terms: List[str] = []

                                        
        for m in re.finditer(r'\bFY(\d{2,4})\b', text, flags=re.IGNORECASE):
            fy_str = m.group(0).upper()
            if fy_str not in fiscal_years:
                fiscal_years.append(fy_str)
                raw_terms.append(fy_str)
            digits = m.group(1)
            full_year = int(digits) if len(digits) == 4 else int("20" + digits)
            if 1990 <= full_year <= 2050:
                years.add(full_year)

                                         
        for m in re.finditer(r'\b(19\d\d|20\d\d)\b', text):
            yr = int(m.group(1))
            if 1990 <= yr <= 2050:
                years.add(yr)
                raw_terms.append(str(yr))

                                            
        for m in re.finditer(r'\b(Q[1-4])(?:\s*(?:FY)?(\d{2,4}))?\b', text, flags=re.IGNORECASE):
            q_str = m.group(0).upper()
            if q_str not in quarters:
                quarters.append(q_str)
                raw_terms.append(q_str)

                                                                    
        range_patterns = [
            r'\bfrom\s+(?:FY)?\d{2,4}\s+to\s+(?:FY)?\d{2,4}\b',
            r'\bbetween\s+(?:FY)?\d{2,4}\s+and\s+(?:FY)?\d{2,4}\b',
            r'\bover\s+the\s+(?:last|past|prior)\s+\d+\s+(?:years|quarters|months)\b',
            r'\bprior\s+(?:fiscal\s+)?year\b',
            r'\bYoY\b|\bQoQ\b',
        ]
        for pat in range_patterns:
            for m in re.finditer(pat, text, flags=re.IGNORECASE):
                r_str = m.group(0)
                if r_str not in date_ranges:
                    date_ranges.append(r_str)
                    raw_terms.append(r_str)

        return TemporalSignal(
            years=sorted(list(years)),
            fiscal_years=fiscal_years,
            quarters=quarters,
            date_ranges=date_ranges,
            raw_temporal_terms=raw_terms,
        )

                                                                       

    def detect_multi_step(
        self,
        text: str,
        financial_signals: FinancialSignal,
        temporal_signals: TemporalSignal,
    ) -> bool:
        """
        Detect whether a question requires multiple distinct retrieval or reasoning phases.
        """
        text_lower = text.lower()

                                                                    
        compound_patterns = [
            r'\band\s+(?:what|how|why|which|explain|compare|where)\b',
            r'\bas\s+well\s+as\s+(?:what|how|why|which|explain|compare)\b',
            r'\balong\s+with\s+(?:what|how|why|the\s+reasons|the\s+drivers)\b',
            r'\band\s+what\s+caused\b',
            r'\band\s+how\s+did\b',
            r'\band\s+why\s+did\b',
            r'\band\s+compare\b',
        ]
        for pat in compound_patterns:
            if re.search(pat, text_lower):
                return True

                                                                                                          
        if len(financial_signals.metrics) >= 2 and len(temporal_signals.years) >= 2:
            return True

                                                              
        has_metric = len(financial_signals.metrics) >= 1
        has_causal = any(kw in text_lower for kw in CAUSAL_KEYWORDS)
        has_and = " and " in text_lower or " as well as " in text_lower
        if has_metric and has_causal and has_and:
            return True

                               
        if ("revenue" in text_lower or "income" in text_lower) and (
            "risk" in text_lower or "guidance" in text_lower
        ):
            return True

        return False

    def decompose_query(
        self,
        normalized_query: str,
        financial_signals: FinancialSignal,
        temporal_signals: TemporalSignal,
        is_multi_step: bool,
        entities: Optional[List[str]] = None,
    ) -> List[str]:
        """
        Decompose multi-part, compound, or multi-step questions into independent sub-queries
        for focused retrieval across document chunks, metrics, and red flags.
        """
        sub_queries: List[str] = []
        clean_q = normalized_query.strip()
        clean_lower = clean_q.lower()

        # 1. Check for explicit conjunction split patterns
        split_patterns = [
            r"\s+(?:and\s+also|and\s+additionally|as\s+well\s+as|along\s+with)\s+",
            r"\s+and\s+(?:what|how|why|which|tell\s+me|explain|compare|where|show\s+me|find|identify|highlight)\s+",
            r"\s*;\s*",
            r"\s*\?\s+(?=[A-Z0-9])",
        ]
        for pat in split_patterns:
            parts = re.split(pat, clean_q, flags=re.IGNORECASE)
            if len(parts) >= 2:
                for p in parts:
                    p_clean = p.strip().rstrip("?.!, ")
                    if p_clean and len(p_clean) > 5 and p_clean not in sub_queries:
                        sub_queries.append(p_clean)
                if len(sub_queries) >= 2:
                    return sub_queries[:4]

        # 2. Check for "compare X and tell me / show me Y" or "X and Y" risk/metric combinations
        if " and " in clean_lower:
            and_parts = clean_q.split(" and ")
            if len(and_parts) == 2:
                p1, p2 = and_parts[0].strip(), and_parts[1].strip()
                if len(p1) > 4 and len(p2) > 4:
                    sub_queries.append(p1)
                    sub_queries.append(p2)
                    return sub_queries

        # 3. Check for multiple distinct metrics (e.g. "revenue and debt", "gross margin and operating margin")
        if len(financial_signals.metrics) >= 2:
            ent_str = f" for {entities[0]}" if (entities and len(entities) == 1) else ""
            years_str = f" in {' and '.join(str(y) for y in temporal_signals.years)}" if temporal_signals.years else ""
            for m in financial_signals.metrics[:3]:
                syn = FINANCIAL_METRIC_MAP.get(m, [m])[0]
                sub_queries.append(f"What was {syn}{ent_str}{years_str}?")
            if len(sub_queries) >= 2:
                return sub_queries

        # 4. Multi-entity comparison
        if entities and len(entities) >= 2:
            for ent in entities:
                sub_queries.append(f"{clean_q} for {ent}")
            return sub_queries

        return []

                                                                       

    def detect_follow_up_and_context(
        self,
        text: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
    ) -> Tuple[bool, bool, QueryContextType]:
        """
        Determine if query is an elliptical follow-up or requires conversation context.

        Returns (is_follow_up, requires_context, context_type).
        """
        text_lower = text.lower()

                                             
        for pat in FOLLOW_UP_PATTERNS:
            if re.search(pat, text_lower):
                return True, True, QueryContextType.PREVIOUS_QUERY

                                                                  
                                                                         
        pronoun_match = any(re.search(r'\b' + p + r'\b', text_lower) for p in FOLLOW_UP_PRONOUNS)
        has_named_entity = bool(
            re.search(r'\b(?:revenue|ebitda|income|profit|margin|expenses|debt|cash|apple|microsoft|tesla|amazon|google)\b', text_lower)
        )

                                                         
        if pronoun_match and not has_named_entity:
            return True, True, QueryContextType.PREVIOUS_QUERY

        if re.search(r'\b(?:that|this)\s+(?:year|quarter|period|number|amount|decline|increase)\b', text_lower):
            return True, True, QueryContextType.PREVIOUS_ANSWER

                                                                                     
        words = text.split()
        if len(words) <= 4:
            if re.search(r'\b(?:how\s+about|what\s+about|and\s+in|why|compare|and\s+for)\b', text_lower):
                return True, True, QueryContextType.PREVIOUS_QUERY

                                                                                        
        if conversation_history and len(conversation_history) > 0:
            if text_lower.startswith(("and ", "also ", "furthermore ", "what about ", "how about ")):
                return True, True, QueryContextType.MULTI_TURN

        return False, False, QueryContextType.NONE

                                                                       

    def classify_query(
        self,
        text: str,
        financial_signals: FinancialSignal,
        temporal_signals: TemporalSignal,
        is_multi_step: bool,
        is_follow_up: bool,
    ) -> Tuple[QueryClassification, List[QueryClassification]]:
        """
        Determine the primary and secondary query classifications deterministically.
        """
        text_lower = text.lower()
        secondaries: Set[QueryClassification] = set()

                                            
        if is_multi_step:
            secondaries.add(QueryClassification.MULTI_STEP)

        if is_follow_up:
            secondaries.add(QueryClassification.FOLLOW_UP)

                    
        if any(re.search(r'\b' + re.escape(kw) + r'\b', text_lower) for kw in RISK_KEYWORDS):
            secondaries.add(QueryClassification.RISK)

                      
        if any(kw in text_lower for kw in CAUSAL_KEYWORDS):
            secondaries.add(QueryClassification.CAUSAL)

                          
        if (
            len(financial_signals.comparison_indicators) > 0
            or len(temporal_signals.years) >= 2
            or len(temporal_signals.quarters) >= 2
            or any(kw in text_lower for kw in COMPARISON_KEYWORDS)
        ):
            secondaries.add(QueryClassification.COMPARISON)

                     
        if any(kw in text_lower for kw in TREND_KEYWORDS) or len(temporal_signals.date_ranges) > 0:
            secondaries.add(QueryClassification.TREND)

                                
        if len(financial_signals.metrics) > 0 or len(financial_signals.currencies) > 0:
            secondaries.add(QueryClassification.FINANCIAL_METRIC)

                               
        if any(kw in text_lower for kw in DOCUMENT_LOOKUP_KEYWORDS):
            secondaries.add(QueryClassification.DOCUMENT_LOOKUP)

                          
        if any(text_lower.startswith(kw) or f" {kw} " in text_lower for kw in DEFINITION_KEYWORDS):
            secondaries.add(QueryClassification.DEFINITION)

                       
        if any(kw in text_lower for kw in SUMMARY_KEYWORDS):
            secondaries.add(QueryClassification.SUMMARY)

                                                             
        if re.search(r'\b(?:what\s+was|what\s+is|what\s+were|how\s+much|when|who)\b', text_lower):
            secondaries.add(QueryClassification.FACTUAL)

                                                                     
        primary = QueryClassification.UNKNOWN

        if is_follow_up and len(text.split()) <= 4:
            primary = QueryClassification.FOLLOW_UP
        elif QueryClassification.RISK in secondaries:
            primary = QueryClassification.RISK
        elif QueryClassification.CAUSAL in secondaries:
            primary = QueryClassification.CAUSAL
        elif QueryClassification.COMPARISON in secondaries:
            primary = QueryClassification.COMPARISON
        elif QueryClassification.TREND in secondaries:
            primary = QueryClassification.TREND
        elif QueryClassification.DOCUMENT_LOOKUP in secondaries:
            primary = QueryClassification.DOCUMENT_LOOKUP
        elif QueryClassification.DEFINITION in secondaries:
            primary = QueryClassification.DEFINITION
        elif QueryClassification.SUMMARY in secondaries:
            primary = QueryClassification.SUMMARY
        elif QueryClassification.FINANCIAL_METRIC in secondaries:
            primary = QueryClassification.FINANCIAL_METRIC
        elif QueryClassification.FACTUAL in secondaries:
            primary = QueryClassification.FACTUAL
        elif is_multi_step:
            primary = QueryClassification.MULTI_STEP
        elif secondaries:
            primary = list(secondaries)[0]

                                                            
        secondary_list = [c for c in secondaries if c != primary]

        return primary, secondary_list

                                                                       

    def expand_query(
        self,
        normalized_query: str,
        financial_signals: FinancialSignal,
        temporal_signals: Optional[TemporalSignal] = None,
        entities: Optional[List[str]] = None,
    ) -> List[str]:
        """
        Generate retrieval-oriented reformulations using financial domain synonyms.
        Crucially: does NOT invent unsupported facts or numbers.
        """
        expansions: List[str] = []
        query_lower = normalized_query.lower()

        for term, synonyms in QUERY_EXPANSION_DICTIONARY.items():
            pattern = r'\b' + re.escape(term) + r'\b'
            if re.search(pattern, query_lower):
                for syn in synonyms[:2]:
                    expanded = re.sub(pattern, syn, normalized_query, flags=re.IGNORECASE)
                    if expanded != normalized_query and expanded not in expansions:
                        expansions.append(expanded)

        for metric in financial_signals.metrics:
            if metric in FINANCIAL_METRIC_MAP:
                synonyms = FINANCIAL_METRIC_MAP[metric]
                primary_name = synonyms[0]
                if primary_name not in query_lower:
                    expansions.append(f"{normalized_query} ({primary_name})")

        if "risk" in query_lower and "risk factors" not in query_lower:
            expansions.append(normalized_query.replace("risk", "risk factors").replace("risks", "risk factors"))

        # Add temporal context if years are present in temporal_signals but missing in query
        if temporal_signals and temporal_signals.years:
            missing_years = [str(y) for y in temporal_signals.years if str(y) not in query_lower]
            if missing_years:
                years_str = " ".join(missing_years)
                expansions.append(f"{normalized_query} {years_str}")

        return expansions[:6]                              

                                                                       

    def _generate_retrieval_hints(
        self,
        classification: QueryClassification,
        financial_signals: FinancialSignal,
        temporal_signals: TemporalSignal,
    ) -> Dict[str, Any]:
        """
        Generate operational hints for Phase 3A Retrieval (e.g. section suggestion).
        """
        hints: Dict[str, Any] = {}

                      
        if classification == QueryClassification.RISK:
            hints["suggested_section"] = "risk_factors"
        elif financial_signals.metrics:
            first_metric = financial_signals.metrics[0]
            if first_metric in METRIC_TO_SECTION_HINT:
                hints["suggested_section"] = METRIC_TO_SECTION_HINT[first_metric]

                              
        if temporal_signals.years:
            hints["target_years"] = temporal_signals.years

        if temporal_signals.quarters:
            hints["target_quarters"] = temporal_signals.quarters

                                                                                         
        if financial_signals.currencies or financial_signals.percentages:
            hints["suggested_retrieval_mode"] = "hybrid"
            hints["boost_lexical"] = True

        return hints

                                                                       

    def extract_entities(
        self,
        raw_query: str,
        normalized_query: str,
        history: Optional[List[Dict[str, str]]] = None,
    ) -> List[str]:
        """
        Generic, heuristic-based entity extraction for financial queries.
        Identifies company/entity names, tickers, and comparison targets without hardcoding.
        """
        entities: List[str] = []
        seen: Set[str] = set()

        def _add_entity(name: str):
            clean = name.strip().rstrip(",.?!:;'\"()[]{}").strip()
                                     
            clean = re.sub(r"['\u2019]s$", "", clean, flags=re.IGNORECASE).strip()
            if not clean or len(clean) < 2:
                return
            clean_lower = clean.lower()
            if clean_lower in COMMON_FINANCIAL_STOPWORDS:
                return
                                                                                                           
            if re.match(r'^(?:(?:19|20)\d{2}|fy\s*\d{2,4}|q[1-4]|\d+|[0-9]+%?)$', clean_lower):
                return

                                                                                                
            words = [w for w in re.split(r'[\s\-]+', clean) if w]
            while words and (
                words[-1].lower() in COMMON_FINANCIAL_STOPWORDS
                or re.match(r'^(?:(?:19|20)\d{2}|fy\s*\d{2,4}|q[1-4]|\d+|[0-9]+%?)$', words[-1].lower())
            ):
                words.pop()

            while words and (
                words[0].lower() in COMMON_FINANCIAL_STOPWORDS
                or re.match(r'^(?:(?:19|20)\d{2}|fy\s*\d{2,4}|q[1-4]|\d+|[0-9]+%?)$', words[0].lower())
                or (len(words) > 1 and words[0].islower() and words[0] != "&")
            ):
                words.pop(0)

            if not words:
                return

            clean_candidate = " ".join(words)
            cand_lower = clean_candidate.lower()
            if cand_lower in COMMON_FINANCIAL_STOPWORDS or len(clean_candidate) < 2:
                return
            if all(
                w.lower() in COMMON_FINANCIAL_STOPWORDS
                or re.match(r'^(?:(?:19|20)\d{2}|fy\s*\d{2,4}|q[1-4]|\d+|[0-9]+%?)$', w.lower())
                for w in words
            ):
                return

            if cand_lower not in seen:
                seen.add(cand_lower)
                if clean_candidate.islower():
                    clean_candidate = clean_candidate.title()
                entities.append(clean_candidate)

                                                                                                          
        for match in re.finditer(r"\b([A-Za-z0-9\.\&\-]+(?:\s+[A-Za-z0-9\.\&\-]+)*)['\u2019]s\b", raw_query):
            cand = match.group(1).strip()
            _add_entity(cand)

                                                                                                        
        cmp_patterns = [
            r"\b(?:compare|comparing|between)\s+([A-Za-z0-9\.\&\-]+(?:\s+[A-Za-z0-9\.\&\-]+)*?)\s+(?:and|with|versus|vs\.?)\s+([A-Za-z0-9\.\&\-]+(?:\s+[A-Za-z0-9\.\&\-]+)*)",
            r"\b([A-Za-z0-9\.\&\-]+(?:\s+[A-Za-z0-9\.\&\-]+)*?)\s+(?:versus|vs\.?)\s+([A-Za-z0-9\.\&\-]+(?:\s+[A-Za-z0-9\.\&\-]+)*)",
        ]
        for pat in cmp_patterns:
            for match in re.finditer(pat, raw_query, flags=re.IGNORECASE):
                e1 = match.group(1).strip()
                e2 = match.group(2).strip()
                _add_entity(e1)
                _add_entity(e2)

                                                                                         
        suffix_pat = r"\b([A-Z][a-zA-Z0-9\.\&\-]*(?:\s+[A-Z][a-zA-Z0-9\.\&\-]*)*\s+(?:Inc\.?|Corp\.?|Corporation|Ltd\.?|LLC|Plc|Group|Holdings|Technologies|Motors|Pharma|Energy|Bank|Co\.?))\b"
        for match in re.finditer(suffix_pat, raw_query):
            _add_entity(match.group(1))

                                                                                                   
        for match in re.finditer(r"\$([A-Za-z]{1,5})\b", raw_query):
            _add_entity(match.group(1).upper())

                                                                                              
        tokens = raw_query.split()
        for idx, token in enumerate(tokens):
            clean_tok = token.strip(",.?!:;'\"()[]{}")
            clean_tok_no_poss = re.sub(r"['\u2019]s$", "", clean_tok)
            if clean_tok_no_poss and clean_tok_no_poss[0].isupper():
                tok_lower = clean_tok_no_poss.lower()
                if tok_lower not in COMMON_FINANCIAL_STOPWORDS:
                                                                                                  
                    if idx == 0 and not clean_tok_no_poss.isupper():
                        continue
                    _add_entity(clean_tok_no_poss)

                                                                                       
        if not entities and history:
            for turn in reversed(history):
                if turn.get("role") != "user":
                    continue
                prev_text = turn.get("content", "")
                # 1. Possessive match (e.g. "Apple's", "BBBY's", "Microsoft's")
                for match in re.finditer(r"\b([A-Za-z0-9\.\&\-]+(?:\s+[A-Za-z0-9\.\&\-]+)*)['\u2019]s\b", prev_text):
                    _add_entity(match.group(1).strip())

                # 2. Company suffix pattern in history (e.g. "Bed Bath & Beyond Inc.")
                if not entities:
                    for match in re.finditer(suffix_pat, prev_text):
                        _add_entity(match.group(1).strip())

                # 3. Ticker pattern in history (e.g. "$AAPL", "$BBBY")
                if not entities:
                    for match in re.finditer(r"\$([A-Za-z]{1,5})\b", prev_text):
                        _add_entity(match.group(1).upper())

                # 4. Multi-word capitalized phrases in user turns (e.g. "Bed Bath & Beyond")
                if not entities:
                    for match in re.finditer(r"\b([A-Z][a-zA-Z0-9\.\-]*(?:\s+(?:&|and|[A-Z][a-zA-Z0-9\.\-]*))+)\b", prev_text):
                        cand = match.group(1).strip()
                        _add_entity(cand)

                if entities:
                    break

                                                                                                                          
        multi_word_entities = [e for e in entities if len(e.split()) > 1]
        if multi_word_entities:
            filtered_entities = []
            for e in entities:
                                                                                                      
                is_sub_fragment = False
                if len(e.split()) == 1:
                    e_low = e.lower()
                    for parent in multi_word_entities:
                        if e_low != parent.lower() and re.search(r'\b' + re.escape(e_low) + r'\b', parent.lower()):
                            is_sub_fragment = True
                            break
                if not is_sub_fragment:
                    filtered_entities.append(e)
            entities = filtered_entities

        return entities


                                                                       

query_understanding_service = QueryUnderstandingService()
