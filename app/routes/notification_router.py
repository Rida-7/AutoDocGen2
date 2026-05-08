from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/notifications/{user_id}")
async def get_all_notifications(user_id: str, request: Request):

    db = request.app.state.db

    notifications = []

    cursor = (
        db["notifications"]
        .find({"user_id": user_id})
        .sort("created_at", -1)
        .limit(50)
    )

    async for n in cursor:
        n["_id"] = str(n["_id"])
        notifications.append(n)

    # -----------------------------
    # GROUP BY SOURCE (IMPORTANT)
    # -----------------------------
    grouped = {
        "trello": [],
        "github": []
    }

    unread_count = 0

    for n in notifications:

        if not n.get("is_read"):
            unread_count += 1

        source = n.get("source", "trello")

        if source not in grouped:
            grouped[source] = []

        grouped[source].append(n)

    return {
        "notifications": grouped,
        "unread_count": unread_count
    }
