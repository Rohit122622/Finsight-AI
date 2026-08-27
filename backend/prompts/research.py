"""
FinSentry AI — Phase 3D Research Prompt Template.

Formats structured runtime context from Phase 3B (Query Understanding) and
Phase 3C (Context Building) with strict delimiter separation.
"""

from typing import Optional

from schemas.context import ResearchContext
from schemas.prompt import PromptConfiguration
from schemas.query_understanding import QueryUnderstandingResult


def build_research_prompt(
    query: str,
    context: ResearchContext,
    query_understanding: Optional[QueryUnderstandingResult] = None,
    config: Optional[PromptConfiguration] = None,
) -> str:
    """
    Assemble the research task and context sections with clear structural boundaries:
      <USER_QUESTION>
      <QUERY_UNDERSTANDING>
      <SOURCE_EVIDENCE>
      <CONVERSATION_CONTEXT>
      <SESSION_MEMORY>
    """
    qu = query_understanding or context.query_understanding

                              
    user_section = f"""<USER_QUESTION>
{query.strip()}
</USER_QUESTION>"""

                                    
    qu_parts = []
    if qu:
        qu_parts.append(f"Intent Classification: {qu.classification.value}")
        if qu.secondary_classifications:
            qu_parts.append(f"Secondary Intents: {', '.join([c.value for c in qu.secondary_classifications])}")
        if qu.financial_signals.metrics:
            qu_parts.append(f"Target Financial Metrics: {', '.join(qu.financial_signals.metrics)}")
        if qu.temporal_signals.years:
            qu_parts.append(f"Target Years: {', '.join([str(y) for y in qu.temporal_signals.years])}")
        if qu.temporal_signals.quarters:
            qu_parts.append(f"Target Quarters: {', '.join(qu.temporal_signals.quarters)}")
        if qu.is_follow_up:
            qu_parts.append("Conversational Note: Follow-up question requiring conversational context.")
        if qu.is_multi_step:
            qu_parts.append("Complexity: Multi-step financial inquiry.")

    qu_text = "\n".join(qu_parts) if qu_parts else "No specific query signals identified."
    qu_section = f"""<QUERY_UNDERSTANDING>
{qu_text}
</QUERY_UNDERSTANDING>"""

                                                    
    evidence_blocks = []

                                     
    if context.metrics:
        evidence_blocks.append("--- FINANCIAL METRICS ---")
        for m in context.metrics:
            ref_str = f" [Doc: {m.document_reference or 'N/A'}"
            if m.page_number:
                ref_str += f", Page: {m.page_number}"
            ref_str += "]"
            period_str = f" (Period: {m.period})" if m.period else ""
            unit_str = f" {m.unit_or_currency}" if m.unit_or_currency else ""
            evidence_blocks.append(f"- {m.metric_name.upper()}: {m.value}{unit_str}{period_str}{ref_str}")

                            
    if context.comparisons:
        evidence_blocks.append("\n--- COMPARISONS ---")
        for c in context.comparisons:
            change_str = f" Change: {c.percentage_change}" if c.percentage_change else ""
            trend_str = f" Trend: {c.trend}" if c.trend else ""
            evidence_blocks.append(
                f"- {c.metric_name.upper()} ({c.base_period} vs {c.target_period}): "
                f"{c.base_value} -> {c.target_value}{change_str}{trend_str}"
            )

                          
    if context.red_flags:
        evidence_blocks.append("\n--- IDENTIFIED RED FLAGS ---")
        for rf in context.red_flags:
            evidence_blocks.append(f"- [{rf.severity}] {rf.title}: {rf.description} (Ref: {rf.source_reference or 'N/A'})")

                        
    if context.documents:
        evidence_blocks.append("\n--- RETRIEVED DOCUMENT CHUNKS ---")
        for idx, doc in enumerate(context.documents, start=1):
            sec_info = f" | Section: {doc.section}" if doc.section else ""
            page_info = f" | Page: {doc.page_number}" if doc.page_number else ""
            fn_info = f" | File: {doc.document_filename}" if doc.document_filename else ""
            evidence_blocks.append(
                f"[CHUNK_{idx}] ID: {doc.chunk_id} | DocID: {doc.document_id}{fn_info}{sec_info}{page_info} | Score: {doc.score:.3f}\n"
                f"{doc.source_text.strip()}\n"
            )

    evidence_text = "\n".join(evidence_blocks) if evidence_blocks else "No source evidence available."
    source_section = f"""<SOURCE_EVIDENCE>
{evidence_text}
</SOURCE_EVIDENCE>"""

                                                           
    history_blocks = []
    if context.chat_history:
        for msg in context.chat_history:
            history_blocks.append(f"{msg.role.upper()}: {msg.content.strip()}")

    history_text = "\n".join(history_blocks) if history_blocks else "No prior conversation history."
    history_section = f"""<CONVERSATION_CONTEXT>
{history_text}
</CONVERSATION_CONTEXT>"""

                                              
    memory_blocks = []
    if context.session_memory:
        mem = context.session_memory
        if mem.topic:
            memory_blocks.append(f"Research Topic: {mem.topic}")
        if mem.entities:
            memory_blocks.append(f"Active Entities: {', '.join(mem.entities)}")
        if mem.metrics_discussed:
            memory_blocks.append(f"Previously Discussed Metrics: {', '.join(mem.metrics_discussed)}")
        if mem.periods_discussed:
            memory_blocks.append(f"Previously Discussed Periods: {', '.join(mem.periods_discussed)}")

    memory_text = "\n".join(memory_blocks) if memory_blocks else "No session memory recorded."
    memory_section = f"""<SESSION_MEMORY>
{memory_text}
</SESSION_MEMORY>"""

    return f"""{user_section}

{qu_section}

{source_section}

{history_section}

{memory_section}"""
