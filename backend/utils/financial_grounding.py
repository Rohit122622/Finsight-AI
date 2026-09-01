"""
FinSentry AI — Financial Number & Currency Grounding Utility.

Provides robust, production-grade financial number extraction, normalization,
and bidirectional evidence grounding verification across unstructured text,
Markdown tables, and structured disclosures.
"""

import math
import re
from typing import Any, Dict, List, Optional, Set, Tuple


                                                                                             
                                                                                        
FINANCIAL_FIGURE_PATTERN = re.compile(
    r"""
    (?P<prefix>[\$€£¥₹])?\s*                # Optional currency symbol
    (?P<neg_open>[\(\-])?\s*              # Optional negative indicator (bracket or minus)
    (?P<prefix_inner>[\$€£¥₹])?\s*         # Optional currency symbol inside bracket $(100)
    (?P<number>
        \d{1,3}(?:,\d{3})+(?:\.\d+)?      # Comma-formatted numbers: 416,161 or 1,234,567.89
        |
        \d+(?:\.\d+)?                      # Plain or decimal numbers: 416161 or 112.5
    )
    \s*(?P<neg_close>\))?\s*              # Closing negative bracket
    (?P<scale>
        billion|million|thousand|trillion # Full scale words
        |bn|mn|m|b|k                      # Short scale abbreviations
        |\%|percent|percentage|bps        # Percentages
    )?
    """,
    re.VERBOSE | re.IGNORECASE,
)

                                           
YEAR_PATTERN = re.compile(r"^(?:19\d\d|20\d\d)$")


def safe_parse_financial_number(val: Any) -> Optional[float]:
    """
    Safely parse any raw value or string into a float without throwing exceptions.
    NEVER calls float() on empty or malformed strings.
    
    Handles:
      - None, empty strings, whitespace -> None
      - ints and floats (excluding NaN and Inf) -> float
      - Comma-formatted numbers: "383,285" -> 383285.0
      - Currency symbols: "$383,285", "₹50,000", "€1,200.50", "£400" -> float
      - Percentages: "31.6%", "19.8 %" -> 31.6, 19.8
      - Parenthesized negative numbers: "(508)", "$(508)", "($508)", "( 508.50 )" -> -508.0, -508.0, -508.0, -508.5
      - Explicit negative signs: "-508", "-$508", "$-508", "- 508.2" -> -508.0, -508.0, -508.0, -508.2
      - Non-numeric strings / missing indicators: "N/A", "-", "—", "abc", "$", "()" -> None
    """
    if val is None:
        return None
    if isinstance(val, (int, float)):
        if math.isnan(val) or math.isinf(val):
            return None
        return float(val)
    if not isinstance(val, str):
        try:
            val = str(val)
        except Exception:
            return None

    s = val.strip()
    if not s:
        return None

    s_lower = s.lower()
    if s_lower in {"none", "null", "n/a", "na", "nil", "-", "—", "--", "–", "unavailable", "unknown", "nan", "inf", "-inf"}:
        return None

    # Check for negative indication via parentheses or negative sign
    is_neg = False
    if s.startswith("(") and s.endswith(")"):
        is_neg = True
        s = s[1:-1].strip()
    elif s.startswith("-") or s.endswith("-"):
        is_neg = True
        s = s.strip("-").strip()
    elif "(" in s and ")" in s:
        paren_match = re.search(r'\(\s*([^)]+)\s*\)', s)
        if paren_match:
            is_neg = True
            s = paren_match.group(1).strip()

    # Strip currency symbols, commas, percent signs, and whitespace
    clean_s = re.sub(r'[\$€£¥₹,%\s]', '', s)
    if clean_s.startswith("-"):
        is_neg = True
        clean_s = clean_s[1:].strip()

    if not clean_s:
        return None

    # Validate numeric format
    if re.match(r'^\d+(?:\.\d+)?$', clean_s):
        try:
            num = float(clean_s)
            if math.isnan(num) or math.isinf(num):
                return None
            return -num if is_neg else num
        except (ValueError, TypeError, OverflowError):
            pass

    # Fallback to financial figure extractor
    figs = extract_financial_figures(val)
    if figs:
        num = figs[0].numeric_value
        if math.isnan(num) or math.isinf(num):
            return None
        return float(num)

    return None


class FinancialFigure:
    """Represents an extracted financial numeric figure with parsed semantics."""

    def __init__(
        self,
        raw_text: str,
        number_str: str,
        numeric_value: float,
        currency: Optional[str] = None,
        is_negative: bool = False,
        scale: Optional[str] = None,
        is_percentage: bool = False,
        is_fiscal_year: bool = False,
    ) -> None:
        self.raw_text = raw_text
        self.number_str = number_str
        self.numeric_value = numeric_value
        self.currency = currency
        self.is_negative = is_negative
        self.scale = scale
        self.is_percentage = is_percentage
        self.is_fiscal_year = is_fiscal_year

                                                                    
        self.normalized_digits = number_str.replace(",", "")
                                                       
        try:
            if "." in self.normalized_digits:
                parts = self.normalized_digits.split(".")
                self.formatted_number = f"{int(parts[0]):,}.{parts[1]}"
            else:
                self.formatted_number = f"{int(self.normalized_digits):,}"
        except ValueError:
            self.formatted_number = number_str

    def __repr__(self) -> str:
        return (
            f"FinancialFigure(raw='{self.raw_text}', num='{self.formatted_number}', "
            f"val={self.numeric_value}, curr={self.currency}, scale={self.scale}, "
            f"pct={self.is_percentage}, yr={self.is_fiscal_year})"
        )


def extract_financial_figures(text: str) -> List[FinancialFigure]:
    """
    Extract all financial figures, currencies, percentages, and amounts from text.
    Correctly flags standalone 4-digit calendar/fiscal years so they are not treated as monetary figures.
    Filters out page numbers, note references, and document section indices.
    """
    figures: List[FinancialFigure] = []
    if not text:
        return figures

    # Clean chunk tags, section markers, page indicators, note headers, table numbers to avoid capturing them as financial figures
    clean_text = re.sub(r"\[[\w\s\-\:\.\_\/]+\]", " ", text.strip())
    clean_text = re.sub(r"\(?\b(?:Page|Item|Note|Section|Part|Table|Exhibit|Figure)\s+\d+[A-Za-z0-9\.\(\)\-]*\)?", " ", clean_text, flags=re.IGNORECASE)

    for match in FINANCIAL_FIGURE_PATTERN.finditer(clean_text):
        raw_match = match.group(0).strip()
        num_str = match.group("number")
        if not num_str:
            continue

        prefix = match.group("prefix") or match.group("prefix_inner")
        neg_open = match.group("neg_open")
        neg_close = match.group("neg_close")
        scale = match.group("scale")

        is_neg = bool((neg_open == "(" and neg_close == ")") or (neg_open == "-" and prefix))
        curr = prefix if prefix else None
        
        is_pct = False
        parsed_scale = None
        if scale:
            s_low = scale.lower()
            if s_low in ["%", "percent", "percentage", "bps"]:
                is_pct = True
            elif s_low in ["b", "bn", "billion"]:
                parsed_scale = "billion"
            elif s_low in ["m", "mn", "million"]:
                parsed_scale = "million"
            elif s_low in ["k", "thousand"]:
                parsed_scale = "thousand"
            elif s_low in ["t", "trillion"]:
                parsed_scale = "trillion"

        clean_num_str = num_str.replace(",", "")
        try:
            val = float(clean_num_str)
            if is_neg:
                val = -val
        except ValueError:
            continue

        # Check for fiscal or calendar year
        is_yr = False
        if not curr and not is_pct and not parsed_scale:
            if YEAR_PATTERN.match(clean_num_str):
                start_idx = max(0, match.start() - 15)
                pre_context = clean_text[start_idx:match.start()].lower()
                if any(w in pre_context for w in ["fiscal", "year", "fy", "in ", "dated", "ended", "period"]):
                    is_yr = True
                elif 1990 <= int(clean_num_str) <= 2050:
                    is_yr = True

        # Skip numbers with preceding page / item / note keywords if unadorned
        start_idx = max(0, match.start() - 15)
        pre_context = clean_text[start_idx:match.start()].lower()
        if any(w in pre_context for w in ["page", "item", "note", "section", "part", "table", "figure"]) and not curr and not is_pct:
            continue

        # Skip unformatted standalone plain numbers unless explicitly currency, percent, scale, negative bracket, comma-formatted, or fiscal year
        if not curr and not is_pct and not parsed_scale and not (neg_open == "(" and neg_close == ")") and "," not in num_str and not is_yr:
            # Allow decimal metrics like EPS (e.g. 7.46, 6.11) only if near EPS or per-share context
            if "." in num_str and any(w in pre_context for w in ["eps", "share", "per"]):
                pass
            else:
                continue

        fig = FinancialFigure(
            raw_text=raw_match,
            number_str=num_str,
            numeric_value=val,
            currency=curr,
            is_negative=is_neg,
            scale=parsed_scale,
            is_percentage=is_pct,
            is_fiscal_year=is_yr,
        )
        figures.append(fig)

    return figures


def is_figure_grounded_in_text(figure: FinancialFigure, evidence_text: str) -> bool:
    """
    Verify if a financial figure extracted from a claim is grounded in the evidence text.
    
    Handles:
    - Verbatim match: "$416,161"
    - Whitespace variation: "$ 416,161"
    - Markdown table delimiter separation: "| $ | 416,161 |" or "$ | 416,161"
    - Comma vs plain numbers: "416,161" vs "416161"
    - Parenthesized negative numbers: "(264)" vs "-264"
    - Scaled amounts: "$416,161 million" grounded in table with "416,161" and "in millions" header
    """
    if not evidence_text or not evidence_text.strip():
        return False

                                                        
    if figure.is_fiscal_year:
        return False

    ev_text = evidence_text

                                                  
    if figure.raw_text.lower() in ev_text.lower():
        return True

                                                     
                                                                                                
    formatted_pat = r"(?<!\d)" + re.escape(figure.formatted_number) + r"(?!\d)"
    if re.search(formatted_pat, ev_text):
        return True

                                                 
    digits_pat = r"(?<!\d)" + re.escape(figure.normalized_digits) + r"(?!\d)"
    if re.search(digits_pat, ev_text):
        return True

                                                                                   
    if figure.currency:
        curr_esc = re.escape(figure.currency)
        num_esc = re.escape(figure.formatted_number)
        table_curr_pat = curr_esc + r"(?:\s*\|\s*|\s+)" + num_esc
        if re.search(table_curr_pat, ev_text):
            return True
        
                                
        table_curr_digits_pat = curr_esc + r"(?:\s*\|\s*|\s+)" + re.escape(figure.normalized_digits)
        if re.search(table_curr_digits_pat, ev_text):
            return True

                                                                               
    if figure.is_negative or figure.numeric_value < 0:
        abs_num = figure.formatted_number
        neg_pats = [
            r"\(\s*" + re.escape(abs_num) + r"\s*\)",
            r"\(\s*\$\s*" + re.escape(abs_num) + r"\s*\)",
            r"\$\s*\(\s*" + re.escape(abs_num) + r"\s*\)",
            r"-\s*\$?\s*" + re.escape(abs_num),
        ]
        for pat in neg_pats:
            if re.search(pat, ev_text):
                return True

                                                            
    if figure.is_percentage:
        pct_pat = re.escape(figure.number_str) + r"\s*(?:\%|percent|percentage)"
        if re.search(pct_pat, ev_text, re.IGNORECASE):
            return True

    return False


def check_figure_derivation_from_operands(
    target: FinancialFigure, operands: List[FinancialFigure]
) -> Tuple[bool, Optional[str]]:
    """
    Deterministically verify if an ungrounded figure can be mathematically derived
    from a list of grounded source figures.
    
    Checks:
      1. Subtraction / Difference: |a - b| == target or a - b == target
      2. Addition / Sum: a + b == target
      3. Percentage Change: |a - b| / b * 100 == target
      4. Percentage Ratio / Margin: (a / b) * 100 == target
      5. Multi-operand sum: sum(operands) == target
    """
    if not operands or len(operands) < 1:
        return False, None

    t_val = abs(target.numeric_value)
    op_figs = [f for f in operands if not f.is_fiscal_year]
    op_vals = [f.numeric_value for f in op_figs]
    if not op_vals:
        return False, None

                               
    n = len(op_vals)
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            a = op_vals[i]
            b = op_vals[j]
            abs_a, abs_b = abs(a), abs(b)

                                                              
            diff = abs(abs_a - abs_b)
            if abs(diff - t_val) < 0.01 or (t_val > 0 and abs(diff - t_val) / t_val < 0.005):
                return True, f"Deterministic difference: |{abs_a:g} - {abs_b:g}| = {diff:g}"

            signed_diff = a - b
            if abs(signed_diff - target.numeric_value) < 0.01:
                return True, f"Deterministic difference: {a:g} - {b:g} = {signed_diff:g}"

                               
            s = abs_a + abs_b
            if abs(s - t_val) < 0.01 or (t_val > 0 and abs(s - t_val) / t_val < 0.005):
                return True, f"Deterministic sum: {abs_a:g} + {abs_b:g} = {s:g}"

                                                     
            if abs_b > 0:
                pct_chg = abs(abs_a - abs_b) / abs_b * 100.0
                if abs(pct_chg - t_val) < 0.20 or (t_val > 0 and abs(pct_chg - t_val) / t_val < 0.03):
                    return True, f"Deterministic percentage change: |{abs_a:g} - {abs_b:g}| / {abs_b:g} * 100 = {pct_chg:.2f}%"

                                                        
                ratio_pct = (abs_a / abs_b) * 100.0
                if abs(ratio_pct - t_val) < 0.20 or (t_val > 0 and abs(ratio_pct - t_val) / t_val < 0.03):
                    return True, f"Deterministic ratio: {abs_a:g} / {abs_b:g} * 100 = {ratio_pct:.2f}%"

                                    
    if n >= 3:
        total_sum = sum(abs(v) for v in op_vals)
        if abs(total_sum - t_val) < 0.01 or (t_val > 0 and abs(total_sum - t_val) / t_val < 0.005):
            return True, f"Deterministic component sum: sum = {total_sum:g}"

    return False, None


def verify_all_claim_figures_in_evidence(
    claim_text: str, evidence_texts: List[str]
) -> Tuple[bool, List[FinancialFigure], List[FinancialFigure]]:
    """
    Extract all figures from a claim sentence and verify each against the list of evidence texts.
    Accepts derived mathematical figures (differences, sums, percentage changes, ratios)
    when all underlying operands are independently grounded in verified evidence.
    
    Returns:
        (all_supported, supported_figures, unsupported_figures)
    """
    combined_evidence = " \n ".join(evidence_texts)
    figures = extract_financial_figures(claim_text)
    
                                                                
    metric_figures = [f for f in figures if not f.is_fiscal_year]
    if not metric_figures:
                                          
        return True, [], []

    supported: List[FinancialFigure] = []
    unsupported: List[FinancialFigure] = []

                                                                 
    evidence_figures = extract_financial_figures(combined_evidence)
    grounded_pool = [f for f in evidence_figures if not f.is_fiscal_year]

    for fig in metric_figures:
        if is_figure_grounded_in_text(fig, combined_evidence):
            supported.append(fig)
        else:
            unsupported.append(fig)

                                                                                        
                                                                
    if unsupported and (supported or grounded_pool):
        derivation_operands = supported + [f for f in grounded_pool if not any(f.numeric_value == s.numeric_value for s in supported)]
        still_unsupported: List[FinancialFigure] = []
        for u_fig in unsupported:
            is_derived, _ = check_figure_derivation_from_operands(u_fig, derivation_operands)
            if is_derived:
                supported.append(u_fig)
            else:
                still_unsupported.append(u_fig)
        unsupported = still_unsupported

    all_supported = len(unsupported) == 0
    return all_supported, supported, unsupported


                                                                             

FORECAST_KEYWORDS = {
    "forecast", "project", "projected", "projection", "projections",
    "guidance", "outlook", "expect", "expected", "expects", "expectation",
    "estimate", "estimated", "estimates", "target", "targets", "targeted",
    "plan", "plans", "goal", "goals", "aim", "aims", "anticipate", "anticipated",
}

                                                        
METRIC_SYNONYMS: Dict[str, List[str]] = {
    "revenue": ["revenue", "gross revenue", "net revenue", "top line", "sales", "net sales", "total revenue", "turnover", "total net sales"],
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


def extract_evidence_years(text: str) -> Set[int]:
    """
    Extract all 4-digit calendar or fiscal years (1990-2050) from text.
    """
    if not text:
        return set()
    years: Set[int] = set()
    for m in re.finditer(r"\b(?:FY)?(19\d\d|20\d\d)\b", text, re.IGNORECASE):
        try:
            yr = int(m.group(1))
            if 1990 <= yr <= 2050:
                years.add(yr)
        except ValueError:
            pass
    return years


def is_year_grounded_with_metric(
    target_year: int,
    metric_canonical: str,
    evidence_texts: List[str],
) -> bool:
    """
    Verify that a requested year is grounded in relationship with the requested financial metric.
    
    Verifies:
      requested metric + requested fiscal/calendar year + corresponding figure/forecast
    
    A 4-digit year appearing in an unrelated paragraph or table without any metric or
    forecast context will return False.
    """
    if not evidence_texts:
        return False

    synonyms = METRIC_SYNONYMS.get(metric_canonical.lower(), [metric_canonical.lower()])
    year_str = str(target_year)
    short_fy = f"FY{year_str[-2:]}"
    full_fy = f"FY{year_str}"

    for chunk in evidence_texts:
        chunk_lower = chunk.lower()
                                                
        has_year = (
            year_str in chunk
            or short_fy.lower() in chunk_lower
            or full_fy.lower() in chunk_lower
        )
        if not has_year:
            continue

                                                                
        has_metric = any(syn.lower() in chunk_lower for syn in synonyms)
        if not has_metric:
            continue

                                            
                                                                                         
        if "|" in chunk:
            lines = chunk.split("\n")
            header_lines = [l for l in lines if "|" in l and any(str(y) in l for y in range(1990, 2050))]
            if any(year_str in hl for hl in header_lines):
                                                                                   
                metric_lines = [l for l in lines if "|" in l and any(syn.lower() in l.lower() for syn in synonyms)]
                if metric_lines:
                    return True

                                                                    
                                                                                         
        figures = extract_financial_figures(chunk)
        has_figures = any(not f.is_fiscal_year for f in figures)
        has_forecast = any(kw in chunk_lower for kw in FORECAST_KEYWORDS)

        if has_figures or has_forecast:
            return True

    return False


                                                                             

                                                                                                                                                      
INTERNAL_ID_PATTERN = re.compile(
    r"""
    (?:[\[\(\<【])?\s*
    (?:
        chunk_[\w\-]+                       # chunk_0, chunk_forecast_2030, chunk_58
        |
        [\w\-]+_chunk_[\w\-]+               # 6a8c4589_chunk_58, doc_123_chunk_4
        |
        chk-[\w\-]+                         # chk-107, chk-abc
        |
        doc-[\w\-]+                         # doc-123, doc-xyz
        |
        [a-f0-9]{24}                        # Standalone ObjectId bracket [6a8c4589c126d7d1179bc304]
        |
        [a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12} # Standalone UUID bracket
    )
    (?:\:\d+)?\s*(?:[\]\)\>】])?
    """,
    re.VERBOSE | re.IGNORECASE,
)


def sanitize_user_facing_text(text: str) -> str:
    """
    Sanitize answer text and key points by stripping internal chunk/document ID
    tags while strictly preserving formulas, monetary values, percentages, and clean punctuation.
    """
    if not text:
        return ""

                                              
    cleaned = INTERNAL_ID_PATTERN.sub("", text)

                                 
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)

                                          
    cleaned = re.sub(r"\s+([,\.\?!;:])", r"\1", cleaned)

                                         
    cleaned = re.sub(r"\[\s*\]", "", cleaned)

    return cleaned.strip()

