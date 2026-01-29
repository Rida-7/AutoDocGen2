from fastapi import APIRouter, Request, Response, BackgroundTasks
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
from app.services.workflow_service import execute_workflow

router = APIRouter()



async def process_trello_action(payload: dict):
    """
    Process the Trello action in the background.
    Keep all workflow logic here.
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

    # Save notification to MongoDB
    notification_doc = {
        "user_id": "user1",  # Map member/board to your user_id logic
        "board_id": board.get("id"),
        "board_name": board.get("name"),
        "event_type": event_type,
        "card_name": card.get("name"),
        "changes": {"user": member.get("fullName")},
        "timestamp": datetime.utcnow()
    }
    await notifications_collection.insert_one(notification_doc)

    # Optional: run workflow or additional processing
    # await execute_workflow(user_id, project_id, data, db=db)


# HEAD request for Trello verification
@router.head("/pm")
async def trello_webhook_verify():
    return Response(status_code=200)


# POST request for Trello events
@router.post("/pm")
async def trello_webhook(
    request: Request,
    background_tasks: BackgroundTasks
):
    try:
        payload = await request.json()
    except Exception:
        return Response(status_code=200)

    background_tasks.add_task(
        process_trello_action,
        payload,
        request.app.state.db
    )

    return Response(status_code=200)



# Endpoint to fetch notifications for frontend
@router.get("/notifications/{user_id}")
async def get_notifications(user_id: str):
    notifications = await notifications_collection.find({"user_id": user_id}).sort("timestamp", -1).to_list(100)
    return notifications
