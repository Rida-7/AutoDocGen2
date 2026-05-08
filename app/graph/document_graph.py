from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.mongodb import MongoDBSaver
from typing import TypedDict, Dict, List
import os
from pymongo import MongoClient

from app.graph.nodes.pm_agent import fetch_pm_data_node
from app.graph.nodes.doc_agent import create_docs_node
from app.graph.nodes.doc_finalize_node import finalize_doc_node
from app.graph.nodes.human_review_node import human_review_node
from app.graph.nodes.section_edit_node import edit_section_node

# =====================================================
# MONGODB CHECKPOINTER
# =====================================================
mongo_client = MongoClient(os.getenv("MONGODB_URI"))

checkpointer = MongoDBSaver(
    mongo_client,
    db_name="Doc_Gen",
    collection_name="workflow_checkpoints"
)

# =====================================================
# STATE
# =====================================================
class WorkflowState(TypedDict, total=False):
    project_id: str
    user_id: str
    template: str
    pm_data: Dict
    draft_doc: str
    final_doc: str
    project_name: str
    user_feedback: str
    review_status: str
    is_final: bool
    pdf_headings: List[str]
    selected_headings: List[str]
    new_headings: List[str]
    intent: str
    doc_type: str

# =====================================================
# GRAPH INIT
# =====================================================
graph = StateGraph(WorkflowState)

# =====================================================
# NODE WRAPPERS
# =====================================================
def debug_pm_agent(state):
    print("\n🔥 [pm_agent] ENTER")
    result = fetch_pm_data_node(state)
    print("🔥 [pm_agent] EXIT")
    return result


def debug_finalize(state):
    print("\n🔥 [doc_finalize] ENTER")
    result = finalize_doc_node(state)
    if not isinstance(result, dict):
        raise ValueError("finalize_doc_node must return dict")
    print("🔥 [doc_finalize] FINAL LENGTH:", len(result.get("final_doc", "")))
    print("🔥 [doc_finalize] EXIT")
    return result


# =====================================================
# ROUTING LOGIC
# =====================================================
def route_after_review(state):
    feedback = state.get("user_feedback", "")
    new_headings = state.get("new_headings", [])
    is_final = state.get("is_final", False)

    if is_final:
        print("🟢 Final flag detected → END")
        return END

    if new_headings:
        print("➕ New headings → regenerate full doc")
        return "doc_draft"

    if feedback:
        if len(feedback.split()) < 15:
            print("✏️ Short feedback → edit section")
            return "edit_section"
        else:
            print("🔁 Long feedback → regenerate")
            return "doc_draft"

    print("✅ No changes → END")
    return END


# =====================================================
# GRAPH BUILD
# =====================================================
graph.add_node("pm_agent", debug_pm_agent)
graph.add_node("doc_draft", create_docs_node)
graph.add_node("doc_finalize", debug_finalize)
graph.add_node("human_review", human_review_node)
graph.add_node("edit_section", edit_section_node)

graph.add_edge(START, "pm_agent")
graph.add_edge("pm_agent", "doc_draft")
graph.add_edge("doc_draft", "doc_finalize")
graph.add_edge("doc_finalize", "human_review")

graph.add_conditional_edges("human_review", route_after_review)
graph.add_edge("edit_section", "doc_finalize")

# =====================================================
# COMPILE — two versions
# =====================================================
workflow = graph.compile(checkpointer=checkpointer)  # for /resume
workflow_fresh = graph.compile()                      # for /start-stream (no checkpoint = no duplication)

print("🔥 GRAPH COMPILED SUCCESSFULLY")
