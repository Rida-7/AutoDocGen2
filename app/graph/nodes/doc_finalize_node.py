import re

def remove_duplicate_sections(text: str) -> str:
    pattern = r"(#{1,6}\s.*)"
    parts = re.split(pattern, text)

    seen = set()
    result = []
    current_heading = None

    for part in parts:
        if part.startswith("#"):
            heading = part.strip()

            if heading in seen:
                current_heading = None
                continue

            seen.add(heading)
            current_heading = heading
            result.append(part)
        else:
            if current_heading:
                result.append(part)

    return "".join(result)


def finalize_doc_node(state):
    draft = state.get("draft_doc", "")

    print("=" * 60)
    print("🔍 [finalize] DRAFT INPUT LENGTH:", len(draft))
    print("🔍 [finalize] DRAFT INPUT PREVIEW:\n", draft[:500])
    print("=" * 60)

    if not draft:
        return {"final_doc": "⚠️ No document generated"}

    draft = re.sub(
        r"#{1,6}\s*FINAL DOCUMENT[^\n]*\n*",
        "",
        draft,
        flags=re.IGNORECASE
    ).strip()

    draft = remove_duplicate_sections(draft)

    print("🔍 [finalize] AFTER DEDUP LENGTH:", len(draft))
    print("🔍 [finalize] AFTER DEDUP PREVIEW:\n", draft[:500])
    print("=" * 60)

    feedback = state.get("user_feedback", "")
    if feedback:
        final_doc = f"# FINAL DOCUMENT (IMPROVED)\n\n{draft}\n\n---\n\n## Feedback Applied:\n{feedback}"
    else:
        final_doc = f"# FINAL DOCUMENT\n\n{draft}"

    return {"final_doc": final_doc} 
