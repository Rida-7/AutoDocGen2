# app/db.py
from motor.motor_asyncio import AsyncIOMotorClient
import os

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = os.getenv("DB_NAME", "autodocgen")

client = AsyncIOMotorClient(MONGO_URI)
db = client[DB_NAME]

# Dependency for FastAPI
async def get_db():
    return db
