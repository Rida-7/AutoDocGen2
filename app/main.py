import os
import re
import motor.motor_asyncio
import uvicorn
import httpx

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from dotenv import load_dotenv
from datetime import datetime  

# ------------------ Load ENV ------------------
print("🔥 DEBUG: Loading environment variables...")
load_dotenv()

FRONTEND_URL = os.getenv("FRONTEND_URL")
MONGODB_URI = os.getenv("MONGODB_URI")
DB_NAME = os.getenv("DB_NAME", "Doc_Gen")
PORT = int(os.getenv("PORT", 8080))
BASE_URL = os.getenv("BASE_URL")

TRELLO_API_KEY = os.getenv("TRELLO_API_KEY")
TRELLO_CALLBACK_URL = os.getenv("TRELLO_CALLBACK_URL") or f"{BASE_URL}/pm"

SLACK_CLIENT_ID = os.getenv("SLACK_CLIENT_ID")
SLACK_CLIENT_SECRET = os.getenv("SLACK_CLIENT_SECRET")
SLACK_REDIRECT_URI = os.getenv("SLACK_REDIRECT_URI")

print("🔥 DEBUG: FRONTEND_URL =", FRONTEND_URL)
print("🔥 DEBUG: DB_NAME =", DB_NAME)
print("🔥 DEBUG: PORT =", PORT)

if not MONGODB_URI:
    raise RuntimeError("MONGODB_URI not set")

print("🔥 DEBUG: MongoDB URI loaded successfully")

# ------------------ App ------------------
print("🔥 DEBUG: Initializing FastAPI app...")
app = FastAPI()

# ------------------ CORS ------------------
print("🔥 DEBUG: Configuring CORS...")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "https://autodocgen-production.up.railway.app",
        "https://autodocgenf.netlify.app",
        "https://autodocgen2-production-8e78.up.railway.app"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------ Routers ------------------
print("🔥 DEBUG: Importing routers...")

from app.routes import auth as auth_router
from app.routes import user as user_router
from app.routes import templates as templates_router
from app.routes import generated_docs as generated_docs_router
from app.routes.trello_webhook import router as trello_webhook_router
from app.routes.workflow_human import router as workflow_human_router

from app.routes.slack_auth import router as slack_auth_router
from app.routes.slack_channels import router as slack_channels_router
from app.routes.slack_messages import router as slack_messages_router
# ------------------ GitHub ------------------
from app.routes.github_auth import router as github_auth_router
from app.routes.github_repo_router import router as github_repos_router
from app.routes.github_webhook_router import router as github_webhook_router
from app.routes.notification_router import router as notification_router
from app.routes.subscription_router import router as subscription_router
from app.routes.workspace_router import router as workspace_router




print("🔥 DEBUG: Registering routers...")

app.include_router(auth_router.router, prefix="/auth")
app.include_router(user_router.router, prefix="/api")
app.include_router(templates_router.router, prefix="/templates")
app.include_router(generated_docs_router.router, prefix="/generated-docs")

app.include_router(trello_webhook_router)

app.include_router(slack_auth_router, prefix="/slack/auth")
app.include_router(slack_channels_router, prefix="/api")
app.include_router(slack_messages_router, prefix="/api")
app.include_router(workflow_human_router)
app.include_router(github_auth_router)
app.include_router(github_repos_router)
app.include_router(github_webhook_router)
app.include_router(notification_router)

app.include_router(subscription_router)
app.include_router(workspace_router)

# ------------------ Services ------------------
print("🔥 DEBUG: Loading services...")

from app.services.trello_service import connect_to_trello
from app.models.user_token_model import (
    get_all_user_tokens,
    get_user_token,
    save_user_token
)
from app.services.slack_service import fetch_channels

# ------------------ MongoDB Startup ------------------
@app.on_event("startup")
async def startup():
    print("🔥 DEBUG: Starting MongoDB connection...")

    client = motor.motor_asyncio.AsyncIOMotorClient(MONGODB_URI)
    app.state.mongo_client = client
    app.state.db = client[DB_NAME]
    db = app.state.db

    print("✅ MongoDB connected")

    await db["notifications"].create_index(
        "action_id",
        unique=True,
        sparse=True
    )
    print("🔥 DEBUG: notifications index ensured")

    await db["slack_connections"].create_index(
        [("user_id", 1), ("team_id", 1)],
        unique=True
    )
    print("🔥 DEBUG: slack_connections index ensured")

    users = await get_all_user_tokens(db)
    print(f"🔥 DEBUG: Loaded users = {len(users)}")

    if not users:
        print("⚠️ No users with Trello tokens found")
        return

    if getattr(app.state, "webhooks_registered", False):
        print("🔥 DEBUG: Webhooks already registered, skipping")
        return

    app.state.webhooks_registered = True

    async with httpx.AsyncClient(timeout=20) as client_http:

        for user in users:
            token = user.get("trello_token")
            user_id = user.get("user_id")

            print(f"🔥 DEBUG: Processing user {user_id}")

            if not token:
                print(f"⚠️ DEBUG: No token for user {user_id}")
                continue

            try:
                res = await client_http.get(
                    "https://api.trello.com/1/members/me/boards",
                    params={
                        "key": TRELLO_API_KEY,
                        "token": token,
                        "fields": "id,name"
                    }
                )
                res.raise_for_status()
                boards = res.json()

                print(f"🔥 DEBUG: Boards fetched for {user_id} = {len(boards)}")

            except Exception as e:
                print(f"❌ Failed boards for user {user_id}: {e}")
                continue

            for board in boards:
                await db["board_user_map"].update_one(
                    {"board_id": board["id"]},
                    {"$set": {
                        "user_id": user_id,
                        "board_name": board["name"]
                    }},
                    upsert=True
                )
                print(f"🔥 DEBUG: mapped board {board['name']} -> {user_id}")

# ------------------ Shutdown ------------------
@app.on_event("shutdown")
async def shutdown():
    print("🔥 DEBUG: Shutting down MongoDB connection...")
    app.state.mongo_client.close()

# ------------------ Trello ------------------
@app.get("/trello/connect")
def trello_connect(request: Request):
    user_id = request.query_params.get("user_id")
    print(f"🔥 DEBUG: Trello connect request user_id={user_id}")
    return connect_to_trello(user_id)

@app.get("/trello/callback")
def trello_callback():
    print("🔥 DEBUG: Trello callback hit")
    return RedirectResponse(f"{FRONTEND_URL}/boards")

@app.post("/trello/save_token")
async def trello_save_token(request: Request):
    data = await request.json()
    db = app.state.db

    print(f"🔥 DEBUG: Saving Trello token for user {data.get('user_id')}")

    await save_user_token(
        data["user_id"],
        data["trello_token"],
        db
    )

    return {"status": "success"}

# ------------------ Boards ------------------
@app.get("/trello/boards_with_headings")
async def boards_with_headings(user_id: str):
    print(f"🔥 DEBUG: Fetch boards for user {user_id}")

    db = app.state.db

    token = await get_user_token(user_id, db)
    if not token:
        print("❌ DEBUG: No token found")
        return {"status": "error", "boards": []}

    async with httpx.AsyncClient(timeout=15) as client:
        res = await client.get(
            "https://api.trello.com/1/members/me/boards",
            params={
                "key": TRELLO_API_KEY,
                "token": token,
                "fields": "id,name,desc"
            }
        )
        boards = res.json()

    print(f"🔥 DEBUG: boards received = {len(boards)}")

    docs = await db["generated_docs"].find({"user_id": user_id}).to_list(None)
    doc_map = {d["project_id"]: d for d in docs}

    result = []

    for b in boards:
        raw = doc_map.get(b["id"], {}).get("generated_docs", "")
        headings = re.findall(r"##\s*(.+)", raw)

        result.append({
            "id": b["id"],
            "name": b["name"],
            "desc": b.get("desc", ""),
            "has_generated_doc": b["id"] in doc_map,
            "previous_headings": headings
        })

    return {"status": "success", "boards": result}

# ------------------ Slack Channels ------------------
@app.get("/slack/channels_with_headings")
async def channels_with_headings(user_id: str, team_id: str):
    print(f"🔥 DEBUG: Slack channels request user={user_id}, team={team_id}")

    db = app.state.db

    from app.models.slack_model import get_slack_token

    token = await get_slack_token(user_id, team_id, db)

    if not token:
        print("❌ DEBUG: Slack token missing")
        return {"status": "error", "channels": []}

    data = await fetch_channels(token)

    if not data.get("ok"):
        print("❌ DEBUG: Slack API failed")
        return {"status": "error", "channels": []}

    channels = data.get("channels", [])
    print(f"🔥 DEBUG: Slack channels fetched = {len(channels)}")

    docs = await db["generated_docs"].find({"user_id": user_id}).to_list(None)
    doc_map = {d["project_id"]: d for d in docs}

    result = []

    for ch in channels:
        channel_id = ch["id"]

        raw = doc_map.get(channel_id, {}).get("generated_docs", "")
        headings = re.findall(r"##\s*(.+)", raw)

        result.append({
            "id": channel_id,
            "name": ch["name"],
            "topic": ch.get("topic", {}).get("value", ""),
            "has_generated_doc": channel_id in doc_map,
            "previous_headings": headings,
            "template_key": "default_slack_template",
            "template_name": "Slack Default Template"
        })

    return {"status": "success", "channels": result}

# ------------------ Workflow ------------------

# ------------------ Improve with Feedback ------------------
@app.post("/workflow/improve-with-feedback")
async def improve_with_feedback(request: Request):
    data = await request.json()
    db = request.app.state.db

    print("🔥 DEBUG: Improve with feedback request received")

    user_id = data.get("user_id")
    project_id = data.get("project_id")
    template_name = data.get("template_name")
    feedback = data.get("feedback")
    board_name = data.get("board_name")

    if not all([user_id, project_id, template_name, feedback]):
        print("❌ DEBUG: Missing feedback fields")
        raise HTTPException(status_code=400, detail="Missing required fields")

    # ✅ New docs with visible_to
    doc = await db["generated_docs"].find_one(
        {"visible_to": user_id, "project_id": project_id, "template_name": template_name},
        sort=[("version", -1)]
    )

    # ✅ Always also check old docs without visible_to
    if not doc:
        print("🔥 DEBUG: visible_to miss — trying legacy user_id query")
        doc = await db["generated_docs"].find_one(
            {"user_id": user_id, "project_id": project_id, "template_name": template_name,
             "visible_to": {"$exists": False}},
            sort=[("version", -1)]
        )

    if not doc:
        print("❌ DEBUG: Document not found")
        raise HTTPException(status_code=404, detail="Document not found")

    print("🔥 DEBUG: Sending to Gemini for improvement")

    from langchain_google_genai import ChatGoogleGenerativeAI
    from app.services.doc_storage_service import save_generated_doc

    llm = ChatGoogleGenerativeAI(model='gemini-2.5-flash')

    prompt = f"""
Improve the document based on user feedback.

DOCUMENT:
{doc.get("generated_docs", "")}

FEEDBACK:
{feedback}

Return improved document only.
"""

    result = await llm.ainvoke(prompt)
    improved_doc = result.content if hasattr(result, "content") else str(result)

    # ✅ save_generated_doc handles visible_to, workspace, version, is_latest
    await save_generated_doc(
        db=db,
        user_id=user_id,
        project_id=project_id,
        template_name=template_name,
        content=improved_doc,
        source=doc.get("source", "trello"),
        team_id=doc.get("team_id"),
        is_final=False,
        workspace_name=board_name or doc.get("workspace_name") or doc.get("board_name"),
    )

    # Fetch saved doc to return correct version number
    new_doc = await db["generated_docs"].find_one(
        {"visible_to": user_id, "project_id": project_id,
         "template_name": template_name, "is_latest": True}
    )
    # Legacy fallback for version fetch
    if not new_doc:
        new_doc = await db["generated_docs"].find_one(
            {"user_id": user_id, "project_id": project_id,
             "template_name": template_name, "visible_to": {"$exists": False}},
            sort=[("version", -1)]
        )

    print(f"🔥 DEBUG: New version saved = {new_doc.get('version') if new_doc else '?'}")

    return {
        "status": "success",
        "version": new_doc.get("version") if new_doc else None,
        "generated_docs": improved_doc
    }


# ------------------ Generated Doc ------------------
@app.get("/workflow/generated")
async def get_generated_doc(
    request: Request,
    user_id: str,
    project_id: str,
    template_name: str,
):
    print("🔥 DEBUG: Fetch generated doc request")
    db = request.app.state.db

    # ✅ 1. is_latest via visible_to (new docs — team + solo)
    doc = await db["generated_docs"].find_one(
        {"visible_to": user_id, "project_id": project_id,
         "template_name": template_name, "is_latest": True}
    )

    # ✅ 2. Any version via visible_to
    if not doc:
        doc = await db["generated_docs"].find_one(
            {"visible_to": user_id, "project_id": project_id, "template_name": template_name},
            sort=[("version", -1)]
        )

    # ✅ 3. Old docs without visible_to field — always check
    if not doc:
        print("🔥 DEBUG: visible_to miss — trying legacy user_id query")
        doc = await db["generated_docs"].find_one(
            {"user_id": user_id, "project_id": project_id, "template_name": template_name,
             "visible_to": {"$exists": False}},
            sort=[("version", -1)]
        )

    if not doc:
        print("❌ DEBUG: Document not found")
        return {"status": "not_found", "generated_docs": "", "board_name": ""}
    
    # ✅ Fetch creator name
    creator_name = "Unknown"
    creator_id = doc.get("user_id", "")
    if creator_id:
        from bson import ObjectId
        try:
            creator = await db["users"].find_one(
                {"_id": ObjectId(creator_id)},
                {"name": 1, "email": 1}
            )
            if creator:
                creator_name = creator.get("name") or creator.get("email") or "Unknown"
        except Exception:
            pass

    return {
        "status": "success",
        "template_name": template_name,
        "generated_docs": doc.get("generated_docs", ""),
        "board_name": doc.get("board_name") or doc.get("workspace_name") or "Unknown Board",
        "created_by_name": creator_name,  # ✅
        "version": doc.get("version"),    # ✅
    }

# ------------------ Run ------------------
if __name__ == "__main__":
    print("🔥 DEBUG: Starting Uvicorn server...")
    uvicorn.run("app.main:app", host="0.0.0.0", port=PORT, reload=True)
