import re
from langchain_google_genai import ChatGoogleGenerativeAI
from app.langsmith.load_prompt import (
    load_prompt_from_langsmith,
    TEMPLATE_PROMPT_MAP,
    DEFAULT_PROMPT
)

from langgraph.config import get_stream_writer


def convert_to_sections(text: str):
    pattern = r"(#{1,6}\s.*)"
    parts = re.split(pattern, text)
    sections = {}
    current_heading = "intro"
    buffer = ""

    for part in parts:
        if not part:
            continue

        if part.startswith("#"):
            if buffer:
                sections[current_heading] = buffer.strip()
            current_heading = part.strip()
            buffer = ""
        else:
            buffer += part

    if buffer:
        sections[current_heading] = buffer.strip()

    return sections


async def create_docs_node(state):

    pm_data = state.get("pm_data", {})
    pdf_headings = state.get("pdf_headings", [])
    selected_headings = state.get("selected_headings", [])
    user_feedback = state.get("user_feedback", "")
    doc_type = state.get("doc_type") or state.get("template", "")

    if not pm_data:
        return {"draft_doc": "⚠️ No PM data found", "sections": {}}

    # =========================
    # ✅ TEMPLATE ROUTING LOGIC
    # =========================
    prompt_template = load_prompt_from_langsmith(doc_type)
    prompt_name = TEMPLATE_PROMPT_MAP.get(doc_type, DEFAULT_PROMPT)

    print("📄 DOC TYPE:", doc_type)
    print("🧠 PROMPT USED:", prompt_name)

    strict_instruction = """
YOU ARE A STRICT DOCUMENT EDITOR.
RULES:
1. NEVER create duplicate headings
2. Each heading must appear ONLY ONCE
3. Do NOT repeat any section
4. Keep structure clean and consistent
5. NO placeholders allowed
"""

    feedback_block = ""
    if user_feedback:
        feedback_block = f"""
USER REQUEST:
{user_feedback}

RULES:
- modify only relevant sections
- do NOT rewrite full document
"""

    final_input = f"""
SYSTEM:
{strict_instruction}

{feedback_block}

DOCUMENT:
{str(pm_data)}
"""

    prompt = prompt_template.format(
        cleaned_pm_data=final_input,
        pdf_headings=pdf_headings,
        selected_headings=selected_headings
    )

    # =========================
    # LLM CALL (NO STREAMING)
    # =========================
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", streaming=False)
    result = await llm.ainvoke(prompt)

    # ✅ content ko string mein convert karo pehle
    raw = result.content if hasattr(result, "content") else str(result)
    
    if isinstance(raw, list):
        full_text = " ".join(
            item.get("text", "") if isinstance(item, dict) else str(item)
            for item in raw
        )
    else:
        full_text = str(raw)

    # ✅ HTML cleanup
    full_text = re.sub(r'<br\s*/?>', ' ', full_text)
    full_text = re.sub(r'<[^>]+>', '', full_text)

    print("🔍 [doc_agent] OUTPUT LENGTH:", len(full_text))

    sections = convert_to_sections(full_text)

    return {
        "draft_doc": full_text,
        "sections": sections,
        "doc_type": doc_type,
        "prompt_used": prompt_name   # ✅ useful for debugging
    }
