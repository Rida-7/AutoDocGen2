from fastapi import APIRouter, Request
from collections import defaultdict

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/dashboard")
async def get_dashboard(request: Request):
    db = request.app.state.db

    # ======================================================
    # DOCS STATS
    # ======================================================
    docs_cursor = db["generated_docs"].find({}, {
        "template_name": 1,
        "source": 1,
        "user_id": 1,
        "created_at": 1,
        "is_latest": 1
    })

    total_docs = 0
    template_counts = defaultdict(int)
    source_counts = defaultdict(int)
    unique_users_docs = set()

    async for doc in docs_cursor:
        total_docs += 1
        template_counts[doc.get("template_name", "Unknown")] += 1
        source_counts[doc.get("source", "unknown")] += 1
        unique_users_docs.add(doc.get("user_id"))

    # ======================================================
    # SUBSCRIPTION STATS
    # ======================================================
    sub_cursor = db["subscriptions"].find({}, {
        "plan": 1,
        "docs_used": 1,
        "user_id": 1
    })

    plan_counts = defaultdict(int)
    total_docs_used = 0
    total_subscribed_users = 0

    async for sub in sub_cursor:
        plan_counts[sub.get("plan", "free")] += 1
        total_docs_used += sub.get("docs_used", 0)
        total_subscribed_users += 1

    # ======================================================
    # WORKSPACE STATS
    # ======================================================
    ws_cursor = db["workspaces"].find({}, {
        "name": 1,
        "members": 1,
        "owner_id": 1,
        "invite_code": 1,
        "created_at": 1
    })

    workspaces = []
    total_workspaces = 0
    total_workspace_members = 0

    async for ws in ws_cursor:
        members = ws.get("members", [])
        total_workspaces += 1
        total_workspace_members += len(members)
        workspaces.append({
            "name": ws.get("name", "Unnamed"),
            "member_count": len(members),
            "owner_id": ws.get("owner_id", ""),
            "created_at": str(ws.get("created_at", ""))
        })

    # ======================================================
    # USER STATS
    # ======================================================
    total_users = await db["users"].count_documents({})

    return {
        "overview": {
            "total_users": total_users,
            "total_docs_generated": total_docs,
            "total_workspaces": total_workspaces,
            "total_workspace_members": total_workspace_members,
            "active_subscribers": total_subscribed_users,
        },
        "docs": {
            "by_template": dict(template_counts),
            "by_source": dict(source_counts),
        },
        "subscriptions": {
            "by_plan": dict(plan_counts),
        },
        "workspaces": workspaces
    }
