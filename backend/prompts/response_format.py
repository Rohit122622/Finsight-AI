"""
FinSentry AI — Phase 3D Response Format Instructions Prompt.

Instructs the model to output a structured JSON schema suitable for
downstream parsing and validation in Phase 3E/3G.
"""

from schemas.prompt import PromptConfiguration


def build_response_format_prompt(config: PromptConfiguration) -> str:
    """
    Generate response format instructions defining the required JSON structure.
    """
    return """<RESPONSE_FORMAT>
You must respond with a single, valid JSON object strictly matching the following schema.
Do NOT wrap the JSON in Markdown code fences if raw output is expected, or use standard ```json ... ``` formatting.

{
  "answer": "Clear, professional financial answer with inline chunk citations (e.g. [chunk_id]).",
  "citations": [
    {
      "chunk_id": "Exact chunk ID from <SOURCE_EVIDENCE>",
      "document_id": "Parent document ID",
      "quoted_snippet": "Verbatim short quote from chunk supporting the claim",
      "claim": "Specific factual claim supported by this citation"
    }
  ],
  "confidence": 0.95, // Numerical confidence score between 0.0 and 1.0 based on evidence strength
  "key_points": [
    "Key financial finding 1",
    "Key financial finding 2"
  ],
  "limitations": [
    "Any missing information, unverified periods, or constraints in available evidence"
  ]
}
</RESPONSE_FORMAT>"""
