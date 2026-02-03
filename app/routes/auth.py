# app/routes/auth.py
import os
import httpx
from fastapi import APIRouter, Request, Response, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from app.models.user_model import find_user_by_email, create_user
from app.utils.crypto import encrypt, decrypt
import bcrypt
import jwt
from datetime import datetime, timedelta
from typing import Optional
from pydantic import BaseModel, EmailStr

router = APIRouter()

JWT_SECRET = os.getenv("JWT_SECRET", "devsecret")
JWT_EXPIRES_IN = os.getenv("JWT_EXPIRES_IN", "15m")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
BASE_URL = os.getenv("BASE_URL", "http://localhost:4000")  # used for OAuth redirect URIs


# Models
class LoginPayload(BaseModel):
    email: EmailStr
    password: str


class RegisterPayload(BaseModel):
    email: EmailStr
    password: str
    name: Optional[str] = None


def issue_token(response: Response, user):
    payload = {"id": str(user.get("_id")), "email": user.get("email")}
    try:
        # interpret JWT_EXPIRES_IN as minutes like '15m'
        if isinstance(JWT_EXPIRES_IN, str) and JWT_EXPIRES_IN.endswith("m"):
            minutes = int(JWT_EXPIRES_IN[:-1])
            exp = datetime.utcnow() + timedelta(minutes=minutes)
        else:
            exp = datetime.utcnow() + timedelta(minutes=15)
        payload["exp"] = exp
    except Exception:
        payload["exp"] = datetime.utcnow() + timedelta(minutes=15)

    token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
    response.set_cookie("token", token, httponly=True, secure=(os.getenv("NODE_ENV") == "production"))
    return token


# -------------------------------
# Signup (alias: register)
# -------------------------------
@router.post("/signup")
@router.post("/register")
async def signup(payload: RegisterPayload, request: Request):
    app = request.app

    # Check if user already exists
    existing = await find_user_by_email(app, payload.email)
    if existing:
        raise HTTPException(
            status_code=400,
            detail="Email already registered"
        )

    # Hash password
    pw_hash = bcrypt.hashpw(
        payload.password.encode("utf-8"),
        bcrypt.gensalt()
    ).decode("utf-8")

    # User document
    user_doc = {
        "email": payload.email,
        "name": payload.name,
        "passwordHash": pw_hash,
        "providers": {},
        "createdAt": datetime.utcnow(),
    }

    # Create user in DB
    new_user = await create_user(app, user_doc)

    # Remove sensitive fields
    new_user.pop("passwordHash", None)

    # Convert ObjectId to string
    if "_id" in new_user:
        new_user["_id"] = str(new_user["_id"])

    # Convert datetime to string (🔥 FIX)
    if "createdAt" in new_user and isinstance(new_user["createdAt"], datetime):
        new_user["createdAt"] = new_user["createdAt"].isoformat()

    # Create response
    resp = JSONResponse(
        content={
            "message": "User registered successfully",
            "user": new_user
        }
    )

    # Issue JWT cookie
    issue_token(resp, new_user)

    return resp



# -------------------------------
# Signin (alias: login)
# -------------------------------
@router.post("/signin")
@router.post("/login")
async def signin(payload: LoginPayload, request: Request):
    app = request.app
    user = await find_user_by_email(app, payload.email)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    pw_hash = user.get("passwordHash", "")
    if not bcrypt.checkpw(payload.password.encode("utf-8"), pw_hash.encode("utf-8")):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # remove sensitive fields
    user.pop("passwordHash", None)

    # convert ObjectId
    if "_id" in user:
        user["_id"] = str(user["_id"])

    resp = JSONResponse(
        content={
            "message": "Logged in successfully",
            "user": user
        }
    )

    issue_token(resp, user)
    return resp



# -------------------------------
# Google OAuth
# -------------------------------
@router.get("/google")
async def google_auth():
    client_id = os.getenv("GOOGLE_CLIENT_ID", "")
    redirect_uri = BASE_URL + "/auth/google/callback"
    scope = "openid email profile"
    url = (
        "https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={client_id}"
        f"&redirect_uri={redirect_uri}"
        f"&response_type=code"
        f"&scope={scope}"
        f"&access_type=offline&prompt=consent"
    )
    return RedirectResponse(url)

@router.get("/google/callback")
async def google_callback(request: Request):
    code = request.query_params.get("code")

    if not code:
        raise HTTPException(status_code=400, detail="Missing authorization code")

    # Exchange code for token
    token_url = "https://oauth2.googleapis.com/token"

    data = {
        "client_id": os.getenv("GOOGLE_CLIENT_ID"),
        "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": BASE_URL + "/auth/google/callback",
    }

    async with httpx.AsyncClient() as client:
        token_res = await client.post(token_url, data=data)
        token_res.raise_for_status()
        tokens = token_res.json()

    # Get user info
    userinfo_url = "https://www.googleapis.com/oauth2/v2/userinfo"
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    async with httpx.AsyncClient() as client:
        user_res = await client.get(userinfo_url, headers=headers)
        user_res.raise_for_status()
        google_user = user_res.json()

    email = google_user.get("email")
    name = google_user.get("name")

    if not email:
        raise HTTPException(status_code=400, detail="Google account has no email")

    # Find or create user
    app = request.app
    user = await find_user_by_email(app, email)

    if not user:
        user_doc = {
            "email": email,
            "name": name,
            "passwordHash": None,
            "providers": {"google": True},
            "createdAt": datetime.utcnow(),
        }
        user = await create_user(app, user_doc)

    # Create response & issue JWT
    resp = RedirectResponse(url=f"{FRONTEND_URL}/landing")
    issue_token(resp, user)

    return resp



# -------------------------------
# GitHub OAuth
# -------------------------------
@router.get("/github")
async def github_auth():
    client_id = os.getenv("GITHUB_CLIENT_ID", "")
    redirect_uri = BASE_URL + "/auth/github/callback"
    url = (
        "https://github.com/login/oauth/authorize"
        f"?client_id={client_id}&redirect_uri={redirect_uri}&scope=user:email"
    )
    return RedirectResponse(url)

@router.get("/github/callback")
async def github_callback(request: Request):
    code = request.query_params.get("code")

    if not code:
        raise HTTPException(status_code=400, detail="Missing GitHub code")

    # Exchange code for access token
    token_url = "https://github.com/login/oauth/access_token"
    data = {
        "client_id": os.getenv("GITHUB_CLIENT_ID"),
        "client_secret": os.getenv("GITHUB_CLIENT_SECRET"),
        "code": code,
    }
    headers = {"Accept": "application/json"}

    async with httpx.AsyncClient() as client:
        token_res = await client.post(token_url, data=data, headers=headers)
        token_res.raise_for_status()
        tokens = token_res.json()

    access_token = tokens.get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail="GitHub token missing")

    # Fetch user info
    async with httpx.AsyncClient() as client:
        user_res = await client.get(
            "https://api.github.com/user",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        user_res.raise_for_status()
        github_user = user_res.json()

        email_res = await client.get(
            "https://api.github.com/user/emails",
            headers={"Authorization": f"Bearer {access_token}"}
        )
        email_res.raise_for_status()
        emails = email_res.json()

    primary_email = next(
        (e["email"] for e in emails if e.get("primary") and e.get("verified")),
        None
    )

    if not primary_email:
        raise HTTPException(status_code=400, detail="No verified GitHub email")

    # Find or create user
    app = request.app
    user = await find_user_by_email(app, primary_email)

    if not user:
        user_doc = {
            "email": primary_email,
            "name": github_user.get("name") or github_user.get("login"),
            "passwordHash": None,
            "providers": {"github": True},
            "createdAt": datetime.utcnow(),
        }
        user = await create_user(app, user_doc)

    resp = RedirectResponse(url=f"{FRONTEND_URL}/landing")
    issue_token(resp, user)
    return resp

