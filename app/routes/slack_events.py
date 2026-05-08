#slack_events.py
from fastapi import APIRouter, Request, BackgroundTasks, Depends
from datetime import datetime
from app.models.slack_model import get_user_tokens

router = APIRouter()

@router.post("/slack/events")
async def slack_events(request: Request, background_tasks: BackgroundTasks, db=Depends(get_db)):
    body = await request.json()
    if "challenge" in body:
        return {"challenge": body["challenge"]}

    event = body.get("event", {})
    team_id = event.get("team")

    # fetch all users that connected this team
    users = await db["slack_connections"].find({"team_id": team_id}).to_list(None)
    for u in users:
        user_id = u["user_id"]
        background_tasks.add_task(process_slack_event, event, user_id, db)

    return {"ok": True}


async def process_slack_event(event, user_id, db):
    # insert into notifications per user_id
    doc = {
        "user_id": user_id,
        "event": event,
        "is_read": False,
        "created_at": datetime.utcnow()
    }
    await db["slack_notifications"].insert_one(doc)
