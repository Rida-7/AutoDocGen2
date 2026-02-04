# /routes/trello_routes.py
from fastapi import APIRouter, HTTPException, Request, Response, BackgroundTasks, Depends
from app.services.trello_service import register_trello_webhook, get_user_token, get_user_generated_boards
from motor.motor_asyncio import AsyncIOMotorDatabase
from app.db import get_db  # Your MongoDB dependency
from datetime import datetime
from fastapi import APIRouter, HTTPException
from app.services.trello_service import register_trello_webhook, get_user_generated_boards
import os

router = APIRouter(prefix="/trello", tags=["Trello"])

@router.post("/webhook/register")
async def register_webhook(user_id: str, db=Depends(get_db)):
    """
    Register webhooks only for boards linked to this user.
    """
    callback_url = os.getenv("TRELLO_CALLBACK_URL")
    if not callback_url:
        raise HTTPException(status_code=500, detail="WEBHOOK_URL not configured")

    # Fetch all boards registered for this user
    user_boards = await get_user_generated_boards(user_id, db)
    if not user_boards:
        raise HTTPException(status_code=404, detail="No boards registered for this user")

    responses = []
    for board in user_boards:
        # Here board["board_id"] must exist in your `get_user_generated_boards` output
        res = await register_trello_webhook(
            board_id=board["board_id"],
            callback_url=callback_url,
            token=os.getenv("TRELLO_TOKEN"),  # or user-specific token if stored
            key=os.getenv("TRELLO_API_KEY"),
        )
        responses.append({
            "board_id": board["board_id"],
            "status_code": res.status_code if res else 500,
            "text": res.text if res else "Webhook failed"
        })

    return {"message": "Webhooks registered", "details": responses}



# ----------------------------
# Trello webhook verification (HEAD request)
# ----------------------------
@router.head("/pm")
async def trello_webhook_verify():
    return Response(status_code=200)


# ----------------------------
# Process Trello webhook events (POST)
# ----------------------------
async def process_trello_action(payload: dict, db: AsyncIOMotorDatabase):
    """
    Process Trello action in background and save user-specific notifications.
    """
    notifications_collection = db["notifications"]
    action = payload.get("action")
    if not action:
        return

    event_type = action.get("type", "unknown")
    data = action.get("data", {})
    board = data.get("board", {})
    card = data.get("card", {})
    list_before = data.get("listBefore", {})
    list_after = data.get("listAfter", {})
    member = action.get("memberCreator", {})

    print("\n🔔 TRELLO BOARD CHANGE DETECTED")
    print(f"Event Type : {event_type}")
    print(f"Board      : {board.get('name', 'Unknown')} ({board.get('id', 'Unknown')})")
    print(f"Card       : {card.get('name', 'Unknown')}")
    print(f"User       : {member.get('fullName', 'Unknown')}")
    if list_before or list_after:
        print(f"List Move  : {list_before.get('name', 'Unknown')} → {list_after.get('name', 'Unknown')}")
    print("──────────────────────────────────")

    # Map board to your registered user
    user_boards = await get_user_boards_for_board(board.get("id"), db)
    for user_board in user_boards:
        notification_doc = {
            "user_id": user_board["user_id"],  # specific user
            "board_id": board.get("id"),
            "board_name": board.get("name"),
            "event_type": event_type,
            "card_name": card.get("name"),
            "changes": {"user": member.get("fullName")},
            "timestamp": datetime.utcnow()
        }
        await notifications_collection.insert_one(notification_doc)


# ----------------------------
# Trello webhook POST endpoint
# ----------------------------
@router.post("/pm")
async def trello_webhook(request: Request, background_tasks: BackgroundTasks, db: AsyncIOMotorDatabase = Depends(get_db)):
    try:
        payload = await request.json()
    except Exception:
        return Response(status_code=200)

    background_tasks.add_task(process_trello_action, payload, db)
    return Response(status_code=200)


# ----------------------------
# Fetch user notifications
# ----------------------------
@router.get("/notifications/{user_id}")
async def get_notifications(user_id: str, db: AsyncIOMotorDatabase = Depends(get_db)):
    notifications_collection = db["notifications"]
    notifications = await notifications_collection.find({"user_id": user_id}).sort("timestamp", -1).to_list(100)
    return {"status": "success", "notifications": notifications}


# ----------------------------
# Helper function to get users linked to a board
# ----------------------------
async def get_user_boards_for_board(board_id: str, db):
    return await db["board_user_map"].find(
        {"board_id": board_id}
    ).to_list(length=None)

