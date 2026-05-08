import os
import httpx
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from app.models.github_model import save_github_token

router = APIRouter()

CLIENT_ID = os.getenv("GITHUB_CLIENT_ID")
CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET")
REDIRECT_URI = os.getenv("GITHUB_REDIRECT_URI")


# ================================
# STEP 1: REDIRECT TO GITHUB
# ================================
@router.get("/github/connect")
async def github_connect(user_id: str):

    url = (
        "https://github.com/login/oauth/authorize"
        f"?client_id={CLIENT_ID}"
        f"&scope=repo admin:repo_hook read:user"
        f"&redirect_uri={REDIRECT_URI}"
        f"&state={user_id}"
    )

    return RedirectResponse(url)


# ================================
# STEP 2: CALLBACK FROM GITHUB
# ================================
@router.get("/github/callback")
async def github_callback(request: Request, code: str, state: str):

    user_id = state  # secure way to get user_id

    async with httpx.AsyncClient() as client:
        res = await client.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "code": code,
                "redirect_uri": REDIRECT_URI
            }
        )

    token_data = res.json()

    await save_github_token(request.app.state.db, user_id, token_data)

    # redirect back to frontend
    return RedirectResponse("http://localhost:5173/github/repos")
