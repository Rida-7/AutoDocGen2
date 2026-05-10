from fastapi import APIRouter, HTTPException, Request
from motor.motor_asyncio import AsyncIOMotorDatabase

router = APIRouter(
    tags=["Generated Documents"]
)

# -------------------------------------------------
# Get ALL generated documents for a user (latest first)
# -------------------------------------------------
@router.get("/all")
async def get_all_generated_docs(request: Request, user_id: str):

    db = request.app.state.db
    collection = db["generated_docs"]

    from app.models.subscription_model import get_user_subscription
    sub = await get_user_subscription(user_id, db)
    plan = sub.get("plan", "free")

    workspace = None
    query = {}

    if plan == "team":
        workspace = await db["workspaces"].find_one({"members": user_id})
        if workspace:
            query = {"workspace_id": str(workspace["_id"])}
        else:
            query = {"user_id": user_id}
    else:
        query = {"user_id": user_id}

    cursor = collection.find(query).sort("version", -1)

    # Collect all unique user_ids to batch-fetch names
    docs_list = []
    creator_ids = set()

    async for doc in cursor:
        docs_list.append(doc)
        if doc.get("user_id"):
            creator_ids.add(doc["user_id"])

    # Batch fetch creator names
    creator_map = {}
    if creator_ids:
        user_cursor = db["users"].find(
            {"_id": {"$in": [__import__('bson').ObjectId(uid) for uid in creator_ids if uid]}},
            {"_id": 1, "name": 1, "email": 1}
        )
        async for u in user_cursor:
            creator_map[str(u["_id"])] = u.get("name") or u.get("email") or "Unknown"

    latest_map = {}
    for doc in docs_list:
        key = f"{doc['project_id']}_{doc['template_name']}"
        if key not in latest_map:
            creator_user_id = doc.get("user_id", "")
            latest_map[key] = {
                "id": str(doc["_id"]),
                "project_id": doc["project_id"],
                "template_name": doc["template_name"],
                "version": doc.get("version", 0),
                "generated_docs": doc.get("generated_docs", ""),
                "project_name": doc.get("workspace_name")
                    or doc.get("project_name")
                    or doc.get("board_name")
                    or "Unknown Project",
                "created_at": str(doc.get("created_at", "")),
                "source": doc.get("source", "trello"),
                "team_id": doc.get("team_id"),
                "is_latest": doc.get("is_latest", False),
                # ✅ Owner info — so frontend can show creator name
                "created_by_user_id": creator_user_id,
                "created_by_name": creator_map.get(creator_user_id, "Unknown"),
                # ✅ Pass workspace_id so team doc fetching works
                "workspace_id": doc.get("workspace_id"),
            }

    return {
        "status": "success",
        "count": len(latest_map),
        "documents": list(latest_map.values())
    }


# -------------------------------------------------
# Get documents for a SPECIFIC BOARD (all versions)
# -------------------------------------------------
@router.get("/by-board")
async def get_docs_by_board(
    request: Request,
    user_id: str,
    project_id: str
):
    db: AsyncIOMotorDatabase = request.app.state.db
    collection = db["generated_docs"]

    cursor = collection.find(
        {
            "user_id": user_id,
            "project_id": project_id
        }
    ).sort("version", -1)

    docs = []
    async for doc in cursor:
        docs.append({
            "id": str(doc["_id"]),
            "template_name": doc.get("template_name", "").strip(),
            "version": doc.get("version", 1),
            "board_name": doc.get("board_name", "Unknown Board").strip(),
            "created_at": doc.get("created_at"),
            "generated_docs": doc.get("generated_docs", ""),
        })

    return {
        "status": "success",
        "count": len(docs),
        "documents": docs
    }


# -------------------------------------------------
# Get latest result — supports workspace_id fallback for team docs
# -------------------------------------------------
@router.get("/result")
async def get_result(
    request: Request,
    user_id: str,
    project_id: str,
    template_name: str,
    workspace_id: str = None,   # ✅ NEW optional param
):
    db = request.app.state.db

    # Try by user_id first
    doc = await db["generated_docs"].find_one(
        {"user_id": user_id, "project_id": project_id, "template_name": template_name},
        sort=[("version", -1)]
    )

    # ✅ Fallback: if team member viewing someone else's doc
    if not doc and workspace_id:
        doc = await db["generated_docs"].find_one(
            {"workspace_id": workspace_id, "project_id": project_id, "template_name": template_name},
            sort=[("version", -1)]
        )

    if not doc:
        return {"status": "not_found", "generated_docs": ""}

    return {
        "status": "success",
        "generated_docs": doc["generated_docs"]
    }


# -------------------------------------------------
# Get ALL versions — workspace_id fallback
# -------------------------------------------------
@router.get("/versions")
async def get_versions(
    request: Request,
    user_id: str,
    project_id: str,
    template_name: str,
):
    db = request.app.state.db

    cursor = db["generated_docs"].find(
        {
            "visible_to": user_id,   # ✅ covers owner + all team members
            "project_id": project_id,
            "template_name": template_name,
        }
    ).sort("version", -1)

    versions = []
    async for doc in cursor:
        versions.append({
            "version": doc["version"],
            "content": doc.get("generated_docs", ""),
            "created_at": doc.get("created_at"),
            "is_latest": doc.get("is_latest", False),
        })

    return {"versions": versions}


# -------------------------------------------------
# Get latest (STRICT latest)
# -------------------------------------------------
@router.get("/latest")
async def get_latest(request: Request, user_id: str, project_id: str, template_name: str):

    db = request.app.state.db

    doc = await db["generated_docs"].find_one(
        {
            "user_id": user_id,
            "project_id": project_id,
            "template_name": template_name
        },
        sort=[("version", -1)]
    )

    if not doc:
        return {"status": "not_found"}

    return {
        "status": "success",
        "version": doc.get("version"),
        "generated_docs": doc.get("generated_docs")
    }


# -------------------------------------------------
# 🔥 RESTORE VERSION (FINAL FIXED LOGIC)
# -------------------------------------------------
@router.post("/restore")
async def restore_version(request: Request, payload: dict):

    db = request.app.state.db
    collection = db["generated_docs"]

    user_id = payload["user_id"]
    project_id = payload["project_id"]
    template_name = payload["template_name"]
    version = payload["version"]

    # 1. Find target version
    target_doc = await collection.find_one({
        "user_id": user_id,
        "project_id": project_id,
        "template_name": template_name,
        "version": version
    })

    if not target_doc:
        return {"status": "not_found"}

    # 2. 🔥 REMOVE OLD LATEST
    await collection.update_many(
        {
            "user_id": user_id,
            "project_id": project_id,
            "template_name": template_name
        },
        {"$set": {"is_latest": False}}
    )

    # 3. 🔥 MARK SELECTED VERSION AS LATEST
    await collection.update_one(
        {"_id": target_doc["_id"]},
        {"$set": {"is_latest": True}}
    )

    return {
        "status": "restored",
        "restored_version": version
    }
