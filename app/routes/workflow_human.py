from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from langgraph.types import Command
from app.graph.document_graph import workflow, workflow_fresh, WorkflowState
from app.models.user_token_model import get_user_token
from app.models.slack_model import get_slack_token
from app.services.slack_service import get_channel_name, run_slack_workflow
from app.services.doc_storage_service import save_generated_doc
from app.services.trello_service import get_board_name
from app.models.github_model import get_github_repo_collection
import os
import json
import asyncio

# ✅ ONLY ADDED (GitHub fix)
from app.services.github_context_builder import build_github_context
from app.services.github_code_service import fetch_repo_tree
from app.models.github_model import get_github_token


router = APIRouter(prefix="/workflow")


# ======================================================
# BUILD STATE
# ======================================================
async def build_state(payload: dict, db):

    user_id = payload.get("user_id")
    project_id = payload.get("project_id")
    source = payload.get("source")
    team_id = payload.get("team_id")
    template = payload.get("template", "").strip()
    pdf_headings = payload.get("pdf_headings", [])
    selected_headings = payload.get("selected_headings", [])

    if not user_id or not project_id:
        raise ValueError("Missing user_id or project_id")
    if not template:
        raise ValueError("Template is required")

    pm_data = {}
    project_name = None

    # =========================
    # SLACK SOURCE
    # =========================
    if source == "slack":
        slack_token = await get_slack_token(user_id, team_id, db)
        if not slack_token:
            raise ValueError("Slack not connected")

        slack_result = await run_slack_workflow(
            user_id=user_id,
            team_id=team_id,
            channel_id=project_id,
            db=db
        )

        if slack_result.get("status") != "success":
            raise ValueError("Slack fetch failed")

        conversation = slack_result.get("conversation", "")
        channel_name = await get_channel_name(slack_token, project_id)

        pm_data = {
            "source": "slack",
            "team_id": team_id,
            "channel_id": project_id,
            "conversation": conversation
        }

        project_name = channel_name

    # =========================
    # GITHUB SOURCE (FIXED)
    # =========================
    elif source == "github":

        repo_doc = await db["github_repos"].find_one(
                {"user_id": user_id},
                sort=[("updated_at", -1)]
)

        if not repo_doc:
            raise ValueError("GitHub repo not selected")

        print("USING GITHUB REPO:", repo_doc["repo_full_name"])

        repo_id = repo_doc["repo_id"]
        owner = repo_doc["repo_owner"]
        repo = repo_doc["repo_name"]

        token_doc = await get_github_token(db, user_id)

        if not token_doc:
            raise ValueError("GitHub not connected")

        token = token_doc["access_token"]

        tree = await fetch_repo_tree(token, owner, repo)

        github_context = await build_github_context(
            token,
            owner,
            repo,
            tree
        )

        pm_data = {
            "source": "github",
            "repo_id": repo_id,
            "repo_owner": owner,
            "repo_name": repo,
            "repo_full": f"{owner}/{repo}",
            "github_context": github_context,
        }

        project_id = repo_id
        project_name = f"{owner}/{repo}"

    # =========================
    # TRELLO SOURCE
    # =========================
    else:
        token = await get_user_token(user_id, db)
        if not token:
            raise ValueError("Trello not connected")

        board_name = await get_board_name(user_id, project_id, db)

        pm_data = {
            "source": "trello",
            "board_id": project_id
        }

        project_name = board_name

    return WorkflowState(
        project_id=project_id,
        user_id=user_id,
        template=template,
        doc_type=template.lower().replace(" ", ""),
        project_name=project_name,
        pm_data=pm_data,
        pdf_headings=pdf_headings,
        selected_headings=selected_headings,
        draft_doc="",
        final_doc="",
        user_feedback="",
        user_trello_key=os.getenv("TRELLO_API_KEY", ""),
        user_trello_token=os.getenv("TRELLO_TOKEN", "")
    )


# ======================================================
# STREAMING ENDPOINT (UNCHANGED)
# ======================================================
@router.post("/start-stream")
async def start_workflow_stream(request: Request, payload: dict):

    db = request.app.state.db
    state = await build_state(payload, db)

    config = {
        "configurable": {
            "thread_id": f"{state['user_id']}_{state['project_id']}_{state['template']}"
        }
    }

    async def event_generator():

        yield "data: " + json.dumps({
            "type": "loading",
            "data": "Generating document..."
        }) + "\n\n"

        final_doc = ""

        async for event in workflow_fresh.astream(
            state,
            config=config,
            stream_mode="updates"
        ):

            if not isinstance(event, dict):
                continue

            if "__interrupt__" in event:
                interrupt_data = event["__interrupt__"][0]
                interrupt_value = getattr(interrupt_data, "value", {})

                yield "data: " + json.dumps({
                    "type": "interrupt",
                    "data": {
                        "value": interrupt_value
                    }
                }) + "\n\n"
                return

            for node_output in event.values():
                if isinstance(node_output, dict) and node_output.get("final_doc"):
                    final_doc = node_output["final_doc"]

        if not final_doc:
            final_doc = "⚠️ No document generated"

        chunk_size = 20
        for i in range(0, len(final_doc), chunk_size):
            chunk = final_doc[i:i+chunk_size]

            yield "data: " + json.dumps({
                "type": "token",
                "data": chunk
            }) + "\n\n"

            await asyncio.sleep(0.01)

        await save_generated_doc(
            db=db,
            user_id=state["user_id"],
            project_id=state["project_id"],
            template_name=state["template"],
            content=final_doc,
            source=state["pm_data"].get("source", "trello"),
            team_id=state["pm_data"].get("team_id"),
            workspace_name=state.get("project_name")
        )

        yield "data: " + json.dumps({
            "type": "done",
            "data": final_doc
        }) + "\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


# ======================================================
# NON-STREAM ENDPOINT (UNCHANGED)
# ======================================================
@router.post("/start")
async def start_workflow(request: Request, payload: dict):
    db = request.app.state.db
    state = await build_state(payload, db)

    config = {
        "configurable": {
            "thread_id": f"{state['user_id']}_{state['project_id']}_{state['template']}"
        }
    }

    final_result = None

    async for event in workflow.astream(state, config=config):

        if isinstance(event, dict) and "__interrupt__" in event:
            return {
                "status": "waiting_for_user",
                "interrupt": event["__interrupt__"][0]
            }

        final_result = event

    final_doc = final_result.get("final_doc", "")

    await save_generated_doc(
        db=db,
        user_id=state["user_id"],
        project_id=state["project_id"],
        template_name=state["template"],
        content=final_doc,
        source=state["pm_data"].get("source", "trello"),
        team_id=state["pm_data"].get("team_id"),
        workspace_name=state.get("project_name")
    )

    return {
        "status": "completed",
        "data": {"final_doc": final_doc}
    }


def classify_user_intent(feedback: str):
    text = feedback.lower()

    if "add:" in text:
        return "new_heading"

    if "update" in text or "in section" in text:
        return "edit_section"

    if "improve" in text or "expand" in text or "detail" in text:
        return "refine"

    return "refine"


# ======================================================
# RESUME WORKFLOW
# ======================================================
# ======================================================
# RESUME WORKFLOW
# ======================================================
@router.post("/resume")
async def resume_workflow(request: Request, payload: dict):

    db = request.app.state.db

    user_id = payload.get("user_id")
    project_id = payload.get("project_id")
    template = payload.get("template")
    user_input = payload.get("user_input", "")
    is_final = payload.get("is_final", False)
    source = payload.get("source", "trello")
    team_id = payload.get("team_id")
    new_headings = payload.get("new_headings", [])

    # ✅ IMPORTANT
    existing_final_doc = payload.get("final_doc", "")

    # =====================================================
    # FINAL APPROVAL → DO NOT REGENERATE
    # =====================================================
    if is_final:

        if not existing_final_doc:
            raise ValueError("final_doc is required for saving")

        state = await build_state(payload, db)

        project_name = state.get("project_name") or project_id

        await save_generated_doc(
            db=db,
            user_id=user_id,
            project_id=project_id,
            template_name=template,
            content=existing_final_doc,
            source=source,
            team_id=team_id,
            is_final=True,
            workspace_name=project_name
        )

        print("🟢 Document marked as FINAL")

        return {
            "status": "completed",
            "data": {
                "final_doc": existing_final_doc
            }
        }

    # =====================================================
    # HUMAN REVIEW → REGENERATE
    # =====================================================

    state = await build_state(payload, db)

    state["user_feedback"] = user_input
    state["is_final"] = False
    state["new_headings"] = new_headings
    state["intent"] = classify_user_intent(user_input)

    config = {
        "configurable": {
            "thread_id": f"{user_id}_{project_id}_{template}_resume"
        }
    }

    final_doc = ""

    async for event in workflow_fresh.astream(
        state,
        config=config,
        stream_mode="updates"
    ):

        if not isinstance(event, dict):
            continue

        for node_output in event.values():

            if (
                isinstance(node_output, dict)
                and node_output.get("final_doc")
            ):
                final_doc = node_output["final_doc"]

    if not final_doc:
        final_doc = "⚠️ No document generated"

    project_name = state.get("project_name") or project_id

    await save_generated_doc(
        db=db,
        user_id=user_id,
        project_id=project_id,
        template_name=template,
        content=final_doc,
        source=source,
        team_id=team_id,
        is_final=False,
        workspace_name=project_name
    )

    return {
        "status": "completed",
        "data": {
            "final_doc": final_doc
        }
    }

@router.post("/finalize")
async def finalize_workflow(request: Request, payload: dict):

    db = request.app.state.db

    user_id = payload.get("user_id")
    project_id = payload.get("project_id")
    template = payload.get("template")
    final_doc = payload.get("final_doc")
    source = payload.get("source", "trello")
    team_id = payload.get("team_id")
    project_name = payload.get("project_name") or project_id

    if not user_id or not project_id or not template:
        raise ValueError("Missing required fields")

    if not final_doc:
        raise ValueError("final_doc is required")

    await save_generated_doc(
        db=db,
        user_id=user_id,
        project_id=project_id,
        template_name=template,
        content=final_doc,
        source=source,
        team_id=team_id,
        is_final=True,
        workspace_name=project_name
    )

    return {
        "status": "completed",
        "message": "Final document saved successfully"
    }
