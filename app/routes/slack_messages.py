from fastapi import APIRouter, Depends
from app.db import get_db
from app.models.slack_model import get_slack_token
from app.services.slack_messages import fetch_messages, join_channel

router = APIRouter()


@router.get("/channel/messages")
async def get_messages(user_id: str, team_id: str, channel_id: str, db=Depends(get_db)):

    token = await get_slack_token(db, user_id, team_id)

    if not token:
        return {"status": "error", "message": "Slack not connected"}

    res = await fetch_channel_messages(token, channel_id)

    if not res.get("ok"):
        return {"status": "error", "messages": []}

    messages = res.get("messages", [])

    conversation = "\n".join(
        f"{m.get('user','unknown')}: {m.get('text','')}"
        for m in messages if m.get("text")
    )

    return {
        "status": "success",
        "conversation": conversation,
        "messages": messages
    }
