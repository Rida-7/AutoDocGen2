from fastapi import APIRouter, HTTPException, Request
from motor.motor_asyncio import AsyncIOMotorDatabase

router = APIRouter(tags=["Generated Documents"])


# -------------------------------------------------
# Get ALL generated documents for a user (latest first)
# -------------------------------------------------
@router.get("/all")
async def get_all_generated_docs(request: Request, user_id: str):
    db = request.app.state.db
    collection = db["generated_docs"]

    latest_map = {}

    # ✅ Query 1: new docs with visible_to
    cursor = collection.find({"visible_to": user_id}).sort("version", -1)
    async for doc in cursor:
        key = f"{doc['project_id']}_{doc['template_name']}"
        if key not in latest_map:
            latest_map[key] = {
                "id": str(doc["_id"]),
                "project_id": doc["project_id"],
                "template_name": doc["template_name"],
                "version": doc.get("version", 0),
                "generated_docs": doc.get("generated_docs", ""),
                "project_name": (
                    doc.get("workspace_name")
                    or doc.get("project_name")
                    or doc.get("board_name")
                    or "Unknown Project"
                ),
                "created_at": str(doc.get("created_at", "")),
                "source": doc.get("source", "trello"),
                "team_id": doc.get("team_id"),
                "is_latest": doc.get("is_latest", False),
                "created_by_user_id": doc.get("user_id", ""),
            }

    # ✅ Query 2: ALWAYS run — old docs where visible_to doesn't exist at all
    cursor2 = collection.find({
        "user_id": user_id,
        "visible_to": {"$exists": False}  # only truly old docs
    }).sort("version", -1)

    async for doc in cursor2:
        key = f"{doc['project_id']}_{doc['template_name']}"
        if key not in latest_map:  # don't overwrite newer docs
            latest_map[key] = {
                "id": str(doc["_id"]),
                "project_id": doc["project_id"],
                "template_name": doc["template_name"],
                "version": doc.get("version", 0),
                "generated_docs": doc.get("generated_docs", ""),
                "project_name": (
                    doc.get("workspace_name")
                    or doc.get("project_name")
                    or doc.get("board_name")
                    or "Unknown Project"
                ),
                "created_at": str(doc.get("created_at", "")),
                "source": doc.get("source", "trello"),
                "team_id": doc.get("team_id"),
                "is_latest": doc.get("is_latest", False),
                "created_by_user_id": doc.get("user_id", ""),
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
async def get_docs_by_board(request: Request, user_id: str, project_id: str):
    db: AsyncIOMotorDatabase = request.app.state.db
    collection = db["generated_docs"]

    cursor = collection.find(
        {"visible_to": user_id, "project_id": project_id}
    ).sort("version", -1)

    docs = []
    async for doc in cursor:
        docs.append({
            "id": str(doc["_id"]),
            "template_name": doc.get("template_name", "").strip(),
            "version": doc.get("version", 1),
            "board_name": (
                doc.get("board_name")
                or doc.get("workspace_name")
                or "Unknown Board"
            ).strip(),
            "created_at": doc.get("created_at"),
            "generated_docs": doc.get("generated_docs", ""),
        })

    # Legacy fallback
    if not docs:
        cursor2 = collection.find(
            {"user_id": user_id, "project_id": project_id}
        ).sort("version", -1)
        async for doc in cursor2:
            docs.append({
                "id": str(doc["_id"]),
                "template_name": doc.get("template_name", "").strip(),
                "version": doc.get("version", 1),
                "board_name": (doc.get("board_name") or "Unknown Board").strip(),
                "created_at": doc.get("created_at"),
                "generated_docs": doc.get("generated_docs", ""),
            })

    return {"status": "success", "count": len(docs), "documents": docs}


# -------------------------------------------------
# Get latest result (FAST FETCH)
# -------------------------------------------------
@router.get("/versions")
async def get_versions(request: Request, user_id: str, project_id: str, template_name: str):
    db = request.app.state.db
    seen_ids = set()
    versions = []

    # New docs
    cursor = db["generated_docs"].find(
        {"visible_to": user_id, "project_id": project_id, "template_name": template_name}
    ).sort("version", -1)
    async for doc in cursor:
        seen_ids.add(str(doc["_id"]))
        versions.append({
            "version": doc["version"],
            "content": doc.get("generated_docs", ""),
            "created_at": doc.get("created_at"),
            "is_latest": doc.get("is_latest", False),
        })

    # Old docs — always run
    cursor2 = db["generated_docs"].find({
        "user_id": user_id,
        "project_id": project_id,
        "template_name": template_name,
        "visible_to": {"$exists": False}
    }).sort("version", -1)
    async for doc in cursor2:
        if str(doc["_id"]) not in seen_ids:
            versions.append({
                "version": doc["version"],
                "content": doc.get("generated_docs", ""),
                "created_at": doc.get("created_at"),
                "is_latest": doc.get("is_latest", False),
            })

    versions.sort(key=lambda x: x["version"], reverse=True)
    return {"versions": versions}


@router.get("/result")
async def get_result(request: Request, user_id: str, project_id: str, template_name: str):
    db = request.app.state.db

    doc = await db["generated_docs"].find_one(
        {"visible_to": user_id, "project_id": project_id, "template_name": template_name},
        sort=[("version", -1)]
    )
    if not doc:
        doc = await db["generated_docs"].find_one(
            {"user_id": user_id, "project_id": project_id, "template_name": template_name,
             "visible_to": {"$exists": False}},
            sort=[("version", -1)]
        )
    if not doc:
        return {"status": "not_found"}
    return {"status": "success", "generated_docs": doc["generated_docs"]}


@router.get("/latest")
async def get_latest(request: Request, user_id: str, project_id: str, template_name: str):
    db = request.app.state.db

    doc = await db["generated_docs"].find_one(
        {"visible_to": user_id, "project_id": project_id, "template_name": template_name},
        sort=[("version", -1)]
    )
    if not doc:
        doc = await db["generated_docs"].find_one(
            {"user_id": user_id, "project_id": project_id, "template_name": template_name,
             "visible_to": {"$exists": False}},
            sort=[("version", -1)]
        )
    if not doc:
        return {"status": "not_found"}
    return {"status": "success", "version": doc.get("version"), "generated_docs": doc.get("generated_docs")}


@router.post("/restore")
async def restore_version(request: Request, payload: dict):
    db = request.app.state.db
    collection = db["generated_docs"]

    user_id = payload["user_id"]
    project_id = payload["project_id"]
    template_name = payload["template_name"]
    version = payload["version"]

    target_doc = await collection.find_one({
        "visible_to": user_id, "project_id": project_id,
        "template_name": template_name, "version": version
    })
    if not target_doc:
        target_doc = await collection.find_one({
            "user_id": user_id, "project_id": project_id,
            "template_name": template_name, "version": version,
            "visible_to": {"$exists": False}
        })
    if not target_doc:
        return {"status": "not_found"}

    await collection.update_many(
        {"project_id": project_id, "template_name": template_name},
        {"$set": {"is_latest": False}}
    )
    await collection.update_one(
        {"_id": target_doc["_id"]},
        {"$set": {"is_latest": True}}
    )
    return {"status": "restored", "restored_version": version}