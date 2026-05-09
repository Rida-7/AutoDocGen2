from fastapi import APIRouter, Request, HTTPException
from app.models.workspace_model import (
    create_workspace,
    get_workspace_by_owner,
    get_workspace_by_member,
    join_workspace_by_code,
    remove_member
)
from app.models.subscription_model import get_user_subscription
from bson import ObjectId

router = APIRouter(prefix="/workspace", tags=["Workspace"])

# ======================================================
# CREATE WORKSPACE
# ======================================================
@router.post("/create")
async def create(request: Request, payload: dict):
    db = request.app.state.db
    user_id = payload.get("user_id")
    name = payload.get("name", "My Team Workspace")

    if not user_id:
        raise HTTPException(status_code=400, detail="Missing user_id")

    # Check team plan
    sub = await get_user_subscription(user_id, db)
    if sub.get("plan") != "team":
        raise HTTPException(
            status_code=403,
            detail="Team plan required to create a workspace"
        )

    # Return existing if already created
    existing = await get_workspace_by_owner(user_id, db)
    if existing:
        return {
            "status": "exists",
            "workspace": {
                "name": existing["name"],
                "invite_code": existing["invite_code"],
                "members": existing["members"],
                "member_count": len(existing["members"])
            }
        }

    workspace = await create_workspace(user_id, name, db)

    return {
        "status": "created",
        "workspace": {
            "name": workspace["name"],
            "invite_code": workspace["invite_code"],
            "members": workspace["members"],
            "member_count": len(workspace["members"])
        }
    }

# ======================================================
# JOIN WORKSPACE
# ======================================================
@router.post("/join")
async def join(request: Request, payload: dict):
    db = request.app.state.db
    user_id = payload.get("user_id")
    invite_code = payload.get("invite_code")

    if not user_id or not invite_code:
        raise HTTPException(status_code=400, detail="Missing user_id or invite_code")

    success, message = await join_workspace_by_code(user_id, invite_code, db)

    if not success:
        raise HTTPException(status_code=400, detail=message)

    return {"status": "joined", "message": message}

# ======================================================
# GET MY WORKSPACE
# ======================================================
@router.get("/my")
async def get_my_workspace(user_id: str, request: Request):
    db = request.app.state.db

    workspace = await get_workspace_by_owner(user_id, db)
    is_owner = True

    if not workspace:
        workspace = await get_workspace_by_member(user_id, db)
        is_owner = False

    if not workspace:
        return {"status": "not_found"}

    return {
        "status": "ok",
        "is_owner": is_owner,
        "workspace": {
            "name": workspace["name"],
            "invite_code": workspace["invite_code"] if is_owner else None,
            "member_count": len(workspace["members"]),
            "members": workspace["members"],
            "owner_id": workspace["owner_id"]
        }
    }

# ======================================================
# REMOVE MEMBER
# ======================================================
@router.post("/remove-member")
async def remove(request: Request, payload: dict):
    db = request.app.state.db
    owner_id = payload.get("owner_id")
    member_id = payload.get("member_id")

    if not owner_id or not member_id:
        raise HTTPException(status_code=400, detail="Missing owner_id or member_id")

    success = await remove_member(owner_id, member_id, db)

    if not success:
        raise HTTPException(status_code=400, detail="Could not remove member")

    return {"status": "removed"}

# ======================================================
# MEMBER DETAILS (emails/names for display)
# ======================================================
@router.post("/member-details")
async def get_member_details(request: Request, payload: dict):
    db = request.app.state.db
    member_ids = payload.get("member_ids", [])

    if not member_ids:
        return {"members": []}

    try:
        object_ids = [ObjectId(m) for m in member_ids]
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid member IDs")

    members = []
    async for user in db["users"].find({"_id": {"$in": object_ids}}):
        members.append({
            "user_id": str(user["_id"]),
            "email": user.get("email", ""),
            "name": user.get("name", "")
        })

    return {"members": members}
