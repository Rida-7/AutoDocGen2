from app.services.llm_router import call_llm

async def improve_document_node(state):
    draft = state.get("generated_docs", "")
    review = state.get("review_notes", "")

    prompt = f"""
You are an expert technical writer.

Rewrite the document using the review feedback.

RULES:
- Make it professional
- Add missing sections
- Fix clarity issues
- Improve structure

Original Document:
{draft}

Review Feedback:
{review}
"""

    result = call_llm(prompt, mode="groq")  # ✅ FAST

    return {
        "improved_docs": result.content if hasattr(result, "content") else str(result)
    }
