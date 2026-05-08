from app.services.llm_router import call_llm

async def review_document_node(state):
    draft = state.get("generated_docs", "")

    prompt = f"""
You are a senior project manager.

Critically review the document.

Return structured feedback in JSON:

{{
  "missing_sections": [],
  "improvements": [],
  "clarity_issues": [],
  "overall_score": "1-10"
}}

Document:
{draft}
"""

    result = call_llm(prompt, mode="groq")  # ✅ FAST + CHEAP

    return {
        "review_notes": result.content if hasattr(result, "content") else str(result)
    }
