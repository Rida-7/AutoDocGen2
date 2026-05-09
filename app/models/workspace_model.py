from datetime import datetime
import secrets


async def create_workspace(owner_id: str, name: str, db) -> dict:
    workspace = {
        "owner_id": owner_id,
        "name": name,
        "invite_code": secrets.token_urlsafe(8),
        "members": [owner_id],
        "created_at": datetime.utcnow()
    }
    result = await db["workspaces"].insert_one(workspace)
    workspace["_id"] = str(result.inserted_id)
    return workspace


async def get_workspace_by_owner(owner_id: str, db) -> dict:
    return await db["workspaces"].find_one({"owner_id": owner_id})


async def get_workspace_by_member(user_id: str, db) -> dict:
    return await db["workspaces"].find_one({"members": user_id})


async def join_workspace_by_code(
    user_id: str,
    invite_code: str,
    db
) -> tuple:

    workspace = await db["workspaces"].find_one(
        {"invite_code": invite_code}
    )

    if not workspace:
        return False, "Invalid invite code"

    if user_id in workspace["members"]:
        return False, "You are already a member"

    if len(workspace["members"]) >= 5:
        return False, "Workspace is full"

    # =========================================
    # CHECK OWNER TEAM PLAN
    # =========================================
    owner_sub = await db["subscriptions"].find_one(
        {"user_id": workspace["owner_id"]}
    )

    if not owner_sub or owner_sub.get("plan") != "team":
        return (
            False,
            "Workspace owner does not have Team plan"
        )

    # =========================================
    # ADD MEMBER
    # =========================================
    await db["workspaces"].update_one(
        {"invite_code": invite_code},
        {
            "$push": {
                "members": user_id
            }
        }
    )

    # =========================================
    # 🔥 SYNC MEMBER PLAN TO TEAM
    # =========================================
    await db["subscriptions"].update_one(
        {"user_id": user_id},
        {
            "$set": {
                "plan": "team",
                "is_active": True,
                "workspace_owner_id": workspace["owner_id"],
                "joined_workspace_at": datetime.utcnow()
            }
        },
        upsert=True
    )

    return True, "Successfully joined workspace"

async def remove_member(
    owner_id: str,
    member_id: str,
    db
) -> bool:

    workspace = await db["workspaces"].find_one(
        {"owner_id": owner_id}
    )

    if not workspace:
        return False

    if member_id == owner_id:
        return False

    if member_id not in workspace["members"]:
        return False

    # =========================================
    # REMOVE MEMBER
    # =========================================
    await db["workspaces"].update_one(
        {"owner_id": owner_id},
        {
            "$pull": {
                "members": member_id
            }
        }
    )

    # =========================================
    # 🔥 RESET MEMBER PLAN
    # =========================================
    await db["subscriptions"].update_one(
        {"user_id": member_id},
        {
            "$set": {
                "plan": "free",
                "docs_used": 0,
                "workspace_owner_id": None
            }
        }
    )

    return True
