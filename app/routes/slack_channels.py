from fastapi import APIRouter, Depends
from app.db import get_db
from app.services.slack_service import fetch_channels
from app.models.slack_model import get_slack_token

router = APIRouter()


@router.get("/channels")
async def get_channels(user_id: str, team_id: str, db=Depends(get_db)):

    token = await get_slack_token(user_id, team_id, db)

    if not token:
        return {"status": "error", "message": "Slack not connected"}

    channels = await fetch_channels(token)

    return {
        "status": "success",
        "channels": channels.get("channels", [])
    }
