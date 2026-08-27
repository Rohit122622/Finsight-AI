"""
FinSentry AI — Phase 3D Refusal Instructions Prompt.

Instructs the model on when and how to refuse to speculate when evidence
is insufficient or absent.
"""

from schemas.prompt import PromptConfiguration, RefusalMode


def build_refusal_prompt(config: PromptConfiguration) -> str:
    """
    Generate refusal behavior instructions.
    """
    refusal_behavior = (
        "If <SOURCE_EVIDENCE> does not contain the specific facts, metrics, or periods needed to answer the question, "
        "you MUST state clearly in your answer: 'The provided documents do not contain sufficient information to answer this question.' "
        "Do NOT speculate, guess, or extrapolate."
        if config.refusal_mode == RefusalMode.STRICT_REFUSAL
        else "If evidence is incomplete, answer ONLY the supported portions, clearly declare the missing items in 'limitations', and set confidence appropriately."
    )

    return f"""<REFUSAL_RULES>
1. INSUFFICIENT EVIDENCE HANDLING:
   {refusal_behavior}

2. DISTINGUISHING MISSING EVIDENCE VS. NEGATIVE FINDING:
   - INSUFFICIENT EVIDENCE: The documents do not mention or cover the requested metric, transaction, or period. (Action: Refuse to guess).
   - NEGATIVE FINDING: The documents explicitly state an item was $0, none, not applicable, or not incurred. (Action: Report the explicit zero/none finding with citation).

3. PARTIAL EVIDENCE RULE:
   - If the evidence answers part of the inquiry (e.g. 2023 revenue is provided, but 2024 revenue is missing), provide the verified 2023 figure, state that 2024 is unavailable, and document the missing period under 'limitations'.

4. PROHIBITION ON SPECULATION:
   - NEVER invent a reason for a financial change unless the cause is explicitly stated in <SOURCE_EVIDENCE>.
   - NEVER make forward-looking assumptions presented as reported historical facts.
</REFUSAL_RULES>"""
