from langgraph.types import interrupt

def human_review_node(state):
    print("\n🔥 [human_review] ENTER")

    final_doc = state.get("final_doc", "")

    result = interrupt({
        "message": "Review document. You can give feedback or mark as final or request to add new heading with content based on data.",
        "final_doc": final_doc
    })

    new_headings = result.get("new_headings", []) or []
    selected_headings = state.get("selected_headings", [])

    # ✅ IMPORTANT: FINAL FLAG
    is_final = result.get("is_final", False)

    # 🔥 MERGE HEADINGS
    merged_headings = list(dict.fromkeys(selected_headings + new_headings))

    return {
        "user_feedback": result.get("user_feedback", "") or "",
        "new_headings": new_headings,
        "intent": result.get("intent", "regenerate"),
        "selected_headings": merged_headings,
        "pdf_headings": state.get("pdf_headings", []),

        # ✅ CRITICAL FIX (you were missing this)
        "is_final": is_final
    }
