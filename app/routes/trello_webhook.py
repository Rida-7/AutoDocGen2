# /routes/trello_routes.py
from fastapi import APIRouter, HTTPException
from app.services.trello_service import register_trello_webhook, get_user_token
from app.models.user_token_model import get_user_boards
import os

router = APIRouter(prefix="/trello", tags=["Trello"])

@router.post("/webhook/register")
async def register_webhook(user_id: str):
    """
    Register webhooks only for boards linked to this user.
    """
    callback_url = os.getenv("TRELLO_CALLBACK_URL")
    if not callback_url:
        raise HTTPException(status_code=500, detail="WEBHOOK_URL not configured")

    # Fetch all boards registered for this user
    user_boards = await get_user_boards(user_id)
    if not user_boards:
        raise HTTPException(status_code=404, detail="No boards registered for this user")

    responses = []
    for board in user_boards:
        res = await register_trello_webhook(
            board_id=board["board_id"],
            callback_url=callback_url,
            token=board["trello_token"],
            key=os.getenv("TRELLO_API_KEY"),
        )
        responses.append({
            "board_id": board["board_id"],
            "status_code": res.status_code,
            "text": res.text
        })

    return {"message": "Webhooks registered", "details": responses}
