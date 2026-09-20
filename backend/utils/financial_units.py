"""Canonical financial-unit conversion with source-unit provenance."""

from __future__ import annotations

from typing import Optional, Tuple

MONETARY_METRICS = {
    "revenue", "total_revenue", "net_sales", "gross_profit", "net_income",
    "operating_income", "operating_cash_flow", "free_cash_flow", "total_debt",
    "total_equity", "stockholders_equity", "cash_and_cash_equivalents",
}


def normalize_monetary_metric(metric_name: str, value: Optional[float], unit: Optional[str], currency: Optional[str], reporting_scale: Optional[str]) -> Tuple[Optional[float], Optional[str], Optional[str], Optional[str], Optional[str]]:
    """Return canonical USD-millions value plus immutable source provenance.

    Only explicit monetary statement metrics are scaled; EPS, percentages,
    ratios, and non-monetary values are deliberately left untouched.
    """
    if value is None:
        return value, unit, currency, unit, reporting_scale
    name = (metric_name or "").lower().strip().removeprefix("prior_")
    source_unit = unit
    source_scale = (reporting_scale or "").lower().strip() or None
    normalized_currency = currency or ("USD" if "usd" in (unit or "").lower() else None)
    unit_lower = (unit or "").lower()
    if name not in MONETARY_METRICS or any(token in unit_lower for token in ("%", "percent", "share", "eps", "ratio")):
        return value, unit, currency, source_unit, source_scale
    # The scale declared by the source statement is more authoritative than
    # an agent-supplied unit label.  The latter can be a canonical/default
    # label even when the evidence says "in thousands" (or vice versa).
    # Fall back to the unit only when no source scale was captured.
    scale_text = source_scale or unit_lower
    if "thousand" in scale_text or "000s" in scale_text:
        factor = 1 / 1000.0
    elif "billion" in scale_text:
        factor = 1000.0
    elif "million" in scale_text:
        factor = 1.0
    else:
        # Never infer a source unit solely from the number's magnitude.
        return value, unit, currency, source_unit, source_scale
    if (normalized_currency or "").upper() != "USD":
        return value, unit, currency, source_unit, source_scale
    return round(float(value) * factor, 6), "USD Millions", "USD", source_unit or "USD", source_scale
