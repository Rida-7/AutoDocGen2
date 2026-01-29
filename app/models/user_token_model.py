# backend/app/models/user_token_model.py
from pydantic import BaseModel
from motor.motor_asyncio import AsyncIOMotorDatabase

class UserToken(BaseModel):
    user_id: str
    trello_token: str  # ✅ consistent name

# ✅ Save user token
async def save_user_token(user_id: str, trello_token: str, db: AsyncIOMotorDatabase):
    await db["tokens"].update_one(
        {"user_id": user_id},
        {"$set": {"trello_token": trello_token}},
        upsert=True
    )

# ✅ Get user token
async def get_user_token(user_id: str, db: AsyncIOMotorDatabase):
    doc = await db["tokens"].find_one({"user_id": user_id})
    return doc["trello_token"] if doc else None

# ✅ Get all user tokens (optional)
async def get_all_user_tokens(db: AsyncIOMotorDatabase):
    cursor = db["tokens"].find(
        {}, {"_id": 0, "user_id": 1, "trello_token": 1}
    )
    return [doc async for doc in cursor]
