"""
FinSentry AI — Phase 3D Citation Instructions Prompt.

Instructs the model on strict evidence citation rules, prohibiting fabricated
citations and requiring exact chunk ID and document mappings.
"""

from schemas.prompt import CitationMode, PromptConfiguration


def build_citation_prompt(config: PromptConfiguration) -> str:
    """
    Generate the citation instructions.
    """
    strict_note = (
        "Every single financial number, fact, and assertion MUST be accompanied by an explicit citation reference to the exact chunk ID or metric from <SOURCE_EVIDENCE>."
        if config.citation_mode == CitationMode.STRICT
        else "Include citations to supporting evidence chunks wherever specific financial metrics or facts are stated."
    )

    return f"""<CITATION_RULES>
1. MANDATORY CITATION MAPPING:
   {strict_note}

2. PERMITTED CITATION IDENTIFIERS:
   - Use the exact chunk ID from <SOURCE_EVIDENCE> (e.g., `[chk-12345]`).
   - If citing a financial metric, reference the metric name and period (e.g., `[METRIC: revenue_2024]`).

3. STRICT PROHIBITIONS:
   - NEVER fabricate or guess a citation, document ID, page number, or chunk ID.
   - NEVER cite a document or source that is not explicitly present in <SOURCE_EVIDENCE>.
   - NEVER attribute a claim to a citation if the cited text does not directly support that specific claim.
   - Do NOT cite <CONVERSATION_CONTEXT> as factual proof; conversation is for context only.
</CITATION_RULES>"""
