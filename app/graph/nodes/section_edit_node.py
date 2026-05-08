import re
import json
from langchain_google_genai import ChatGoogleGenerativeAI


# ==========================================================
# 🧩 SPLIT DOCUMENT INTO SECTIONS
# ==========================================================
def split_into_sections(doc: str):
    sections = {}
    current_heading = None
    buffer = []

    for line in doc.split("\n"):
        line_strip = line.strip()

        # FIXED regex (IMPORTANT)
        if re.match(r"^#+\s*.*", line_strip):
            if current_heading:
                sections[current_heading] = "\n".join(buffer).strip()
                buffer = []

            current_heading = line_strip
        else:
            buffer.append(line)

    if current_heading:
        sections[current_heading] = "\n".join(buffer).strip()

    return sections

# ==========================================================
# 🎯 SMART SECTION MATCHING (IMPROVED SCORING)
# ==========================================================
def find_best_section(sections, parsed):
    keywords = parsed.get("keywords", [])

    best_match = None
    best_score = 0

    for heading in sections.keys():
        score = sum(
            2 if k.lower() in heading.lower()
            else 1 if k.lower() in sections[heading].lower()
            else 0
            for k in keywords
        )

        if score > best_score:
            best_score = score
            best_match = heading

    # fallback → if nothing matches, take last section
    return best_match or (list(sections.keys())[-1] if sections else None)


# ==========================================================
# 🧩 REBUILD DOCUMENT (SAFE ORDER)
# ==========================================================
def rebuild_document(original_doc: str, updated_sections: dict):
    output = []

    # preserve original order strictly
    for line in original_doc.split("\n"):
        line_strip = line.strip()

        if line_strip in updated_sections:
            output.append(line_strip)
            output.append(updated_sections[line_strip])
        else:
            output.append(line)

    return "\n".join(output)


# ==========================================================
# ✏️ EDIT SECTION NODE (FINAL INTELLIGENT VERSION)
# ==========================================================
def edit_section_node(state):
    print("\n🔥 [edit_section] ENTER")

    draft_doc = state.get("draft_doc", "")
    instruction = state.get("user_feedback", "")

    if not draft_doc or not instruction:
        return state

    # ======================================================
    # 1. INTENT EXTRACTION (NO HARDCODE)
    # ======================================================
    parsed = {
             "keywords": instruction.split()
             }

    # ======================================================
    # 2. SPLIT DOC
    # ======================================================
    sections = state.get("sections") or split_into_sections(draft_doc)

    if not sections:
        print("❌ No sections found in document")
        return state

    # ======================================================
    # 3. FIND TARGET SECTION (SMART)
    # ======================================================
    target_section = find_best_section(sections, parsed)

    if not target_section or target_section not in sections:
        print("❌ No matching section found")
        return state

    old_content = sections[target_section]

    # ======================================================
    # 4. LLM EDIT (STRICT BUT NATURAL)
    # ======================================================
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash")

    prompt = f"""
You are an intelligent document editor.

TASK:
Modify ONLY this section based on user request.

SECTION:
{target_section}

CURRENT CONTENT:
{old_content}

USER REQUEST:
{instruction}

RULES:
- Do NOT change other sections
- Do NOT add new headings
- Keep formatting consistent
- Apply changes naturally (no rigid templates)
"""

    result = llm.invoke(prompt)

    new_content = result.content if hasattr(result, "content") else str(result)

    # ======================================================
    # 5. UPDATE SECTION
    # ======================================================
    sections[target_section] = new_content.strip()

    # ======================================================
    # 6. REBUILD DOCUMENT
    # ======================================================
    updated_doc = rebuild_document(draft_doc, sections)

    print("✅ Section updated:", target_section)

    # ======================================================
    # 7. RETURN STATE
    # ======================================================
    return {
        "draft_doc": updated_doc,
        "pm_data": state.get("pm_data"),
        "pdf_headings": state.get("pdf_headings"),
        "selected_headings": state.get("selected_headings"),
        "user_feedback": "",
        "new_headings": []
    }
