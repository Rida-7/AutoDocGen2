def create_draft_node(state):
    print("🔥 [doc_draft] ENTER")

    pm_data = state.get("pm_data", {})
    feedback = state.get("user_feedback", "")

    document_type = state.get("template", "Document")

    selected_headings = state.get("selected_headings", [])
    pdf_headings = state.get("pdf_headings", [])

    selected_headings = selected_headings or pdf_headings or []

    conversation = pm_data.get("conversation", "")

    # Simple project name extraction (optional improvement)
    project_name = state.get("project_name") or document_type

    sections = []

    # =====================================================
    # FIRST GENERATION
    # =====================================================
    if not feedback:
        print("🆕 First generation")

        for heading in selected_headings:
            sections.append(f"""
### {heading}

[Auto-generated content for "{heading}" based on project context]

""")

        draft = f"""
# {document_type}

## Project: {project_name}

---

{chr(10).join(sections)}
"""

    # =====================================================
    # REGENERATION (WITH FEEDBACK)
    # =====================================================
    else:
        print("🔁 Regenerating with feedback")

        for heading in selected_headings:
            sections.append(f"""
### {heading}

[Revised content for "{heading}" based on user feedback]

""")

        draft = f"""
# {document_type} (Revised)

## Project: {project_name}

---

{chr(10).join(sections)}
"""

    print("🔥 [doc_draft] EXIT")

    return {"draft_doc": draft}
