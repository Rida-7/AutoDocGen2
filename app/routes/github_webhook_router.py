from fastapi import APIRouter, Request
from app.services.github_change_detector import (
    is_major_github_change
)

from app.services.github_notification_builder import (
    build_github_message
)

from app.models.notification_model import (
    save_notification
)

router = APIRouter()


def build_github_message(payload, important_changes):

    repo = payload["repository"]["full_name"]

    commits = payload.get("commits", [])

    commit_count = len(commits)

    files = "\n".join(
        f"- {f}" for f in important_changes[:10]
    )

    return f"""
🔥 Major GitHub Update Detected

Repository: {repo}

Commits: {commit_count}

Important Changes:
{files}
"""


@router.post("/webhooks/github")
async def github_webhook(request: Request):

    payload = await request.json()

    event = request.headers.get("X-GitHub-Event")

    # -----------------------------
    # ONLY HANDLE PUSH
    # -----------------------------
    if event != "push":
        return {"status": "ignored"}

    # -----------------------------
    # DETECT MAJOR CHANGE
    # -----------------------------
    is_major, important_changes = is_major_github_change(payload)

    if not is_major:
        print("⚪ Minor GitHub change ignored")
        return {"status": "minor_change"}

    # -----------------------------
    # BUILD MESSAGE
    # -----------------------------
    message = build_github_message(
        payload,
        important_changes
    )

    # -----------------------------------
    # FIND REPO
    # -----------------------------------
    repo = payload["repository"]["full_name"]

    # -----------------------------------
    # FIND REPO OWNER IN DB
    # -----------------------------------
    repo_doc = await request.app.state.db["github_repos"].find_one({
        "repo_full_name": repo
    })

    if not repo_doc:
        return {"status": "repo_not_registered"}

    user_id = repo_doc["user_id"]

    # -----------------------------------
    # SAVE NOTIFICATION
    # -----------------------------------
    await save_notification(
        db=request.app.state.db,
        user_id=user_id,
        source="github",
        message=message,
        project_id=repo
    )

    # -----------------------------------
    # HERE:
    # trigger notification / workflow
    # -----------------------------------

    return {
        "status": "major_change_detected"
    }
