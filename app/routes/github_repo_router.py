from fastapi import APIRouter, Request
from app.models.github_model import get_github_token, save_github_repo, save_github_webhook
from app.services.github_service import fetch_user_repos, create_github_webhook
from app.services.github_code_service import fetch_repo_tree, fetch_file
import os

router = APIRouter()


# =========================
# GET USER REPOS
# =========================
@router.get("/github/repos")
async def get_repos(user_id: str, request: Request):

    db = request.app.state.db
    token_doc = await get_github_token(db, user_id)

    if not token_doc:
        return {"error": "GitHub not connected"}

    repos = await fetch_user_repos(token_doc["access_token"])
    return {"repos": repos}


# =========================
# SELECT REPO (FIXED + NON-BLOCKING WEBHOOK)
# =========================
@router.post("/github/select-repo")
async def select_repo(request: Request, payload: dict):

    db = request.app.state.db

    user_id = payload.get("user_id")
    repo = payload.get("repo")

    if not isinstance(repo, dict):
        return {"error": "Invalid repo format"}

    # -------------------------
    # SAVE REPO
    # -------------------------
    await save_github_repo(db, user_id, repo)

    # -------------------------
    # GET TOKEN
    # -------------------------
    token_doc = await get_github_token(db, user_id)

    if not token_doc:
        return {"error": "GitHub not connected"}

    token = token_doc["access_token"]

    # =====================================================
    # 🔥 DEBUG (MANDATORY)
    # =====================================================
    print("FULL REPO OBJECT:", repo)

    # =====================================================
    # 🔧 FIXED OWNER + REPO EXTRACTION
    # =====================================================
    full_name = repo.get("full_name")  # "owner/repo"

    if not full_name:
        raise ValueError("Missing full_name in repo object")

    owner, repo_name = full_name.split("/")

    print("OWNER:", owner)
    print("REPO:", repo_name)

    # -------------------------
    # WEBHOOK CONFIG
    # -------------------------
    webhook_url = os.getenv("GITHUB_WEBHOOK_URL")
    secret = os.getenv("GITHUB_WEBHOOK_SECRET")

    # =====================================================
    # 🔥 NON-BLOCKING WEBHOOK (FIX APPLIED)
    # =====================================================
    webhook_id = None
    webhook_status = "skipped"

    try:
        webhook = await create_github_webhook(
            token,
            owner,
            repo_name,
            webhook_url,
            secret
        )

        webhook_id = webhook.get("id")
        webhook_status = "created"

    except Exception as e:
        msg = str(e)

        # safe ignore cases
        if "already exists" in msg or "422" in msg:
            print("⚠️ Webhook already exists - continuing workflow")
            webhook_status = "exists"
        else:
            print("❌ Webhook failed but ignoring:", msg)
            webhook_status = "failed"

    print("WEBHOOK STATUS:", webhook_status)
    print("WEBHOOK ID:", webhook_id)

    # =====================================================
    # FINAL RESPONSE (NON-BLOCKING)
    # =====================================================
    return {
        "status": "repo_saved",
        "webhook_id": webhook_id,
        "webhook_status": webhook_status,
        "message": "Repo saved successfully (workflow continues regardless of webhook)"
    }


# =========================
# CODE CONTEXT (FOR LLM)
# =========================
@router.get("/github/repo-code-context")
async def get_repo_code_context(user_id: str, request: Request):

    db = request.app.state.db

    token_doc = await get_github_token(db, user_id)
    repo_doc = await db["github_repos"].find_one({"user_id": user_id})

    if not token_doc or not repo_doc:
        return {"error": "missing data"}

    token = token_doc["access_token"]
    owner = repo_doc["repo_owner"]
    repo = repo_doc["repo_name"]

    tree = await fetch_repo_tree(token, owner, repo)

    if not tree or "tree" not in tree:
        return {"error": "Could not fetch repo tree"}

    files = []

    allowed_ext = [".py", ".js", ".ts", ".java", ".go", ".md"]

    for item in tree["tree"]:

        if item["type"] != "blob":
            continue

        if not any(item["path"].endswith(ext) for ext in allowed_ext):
            continue

        if "node_modules" in item["path"]:
            continue

        try:
            content = await fetch_file(token, owner, repo, item["path"])

            files.append({
                "path": item["path"],
                "content": content[:6000]
            })

        except:
            continue

        if len(files) >= 25:
            break

    return {
        "repo": f"{owner}/{repo}",
        "files": files
    }
