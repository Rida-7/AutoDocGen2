# routes/trello_routes.py
from fastapi import APIRouter, HTTPException
from app.services.trello_service import register_trello_webhook
import os

router = APIRouter(prefix="/trello", tags=["Trello"])

@router.post("/webhook/register")
async def register_webhook(board_id: str):
    callback_url = os.getenv("TRELLO_CALLBACK_URL")

    if not callback_url:
        raise HTTPException(
            status_code=500,
            detail="WEBHOOK_URL not configured"
        )

    res = await register_trello_webhook(
        board_id=board_id,
        callback_url=callback_url,
        token=os.getenv("TRELLO_TOKEN"),
        key=os.getenv("TRELLO_API_KEY"),
    )

    if res.status_code not in (200, 201):
        raise HTTPException(
            status_code=res.status_code,
            detail=res.text
        )

    return {"message": "Webhook registered"}
