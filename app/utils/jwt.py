from jose import jwt
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

load_dotenv() 
SECRET = os.getenv("JWT_SECRET")

if not SECRET:
    raise Exception("JWT_SECRET not set in environment variables")
EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRES_IN", 15))
ALGO = "HS256"


def create_access_token(data: dict):
    payload = data.copy()
    payload.update({
        "exp": datetime.utcnow() + timedelta(minutes=EXPIRE_MINUTES),
        "type": "access"
    })
    return jwt.encode(payload, SECRET, algorithm=ALGO)


def create_refresh_token(data: dict):
    payload = data.copy()
    payload.update({
        "exp": datetime.utcnow() + timedelta(days=7),
        "type": "refresh"
    })
    return jwt.encode(payload, SECRET, algorithm=ALGO)


def verify_token(token: str):
    return jwt.decode(token, SECRET, algorithms=[ALGO])