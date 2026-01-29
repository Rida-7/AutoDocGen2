import os
import re
import asyncio
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
import motor.motor_asyncio
import uvicorn
import httpx
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ------------------ Environment Variables ------------------
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
MONGODB_URI = os.getenv("MONGODB_URI")
DB_NAME = os.getenv("DB_NAME", "Doc_Gen")
PORT = int(os.getenv("PORT", 8080))
BASE_URL = os.getenv("BASE_URL")
TRELLO_API_KEY = os.getenv("TRELLO_API_KEY")
TRELLO_CALLBACK_URL = os.getenv("TRELLO_CALLBACK_URL") or f"{BASE_URL}/pm"

if not MONGODB_URI:
    raise RuntimeError("MONGODB_URI environment variable not set!")
if not TRELLO_API_KEY:
    raise RuntimeError("TRELLO_API_KEY environment variable not set!")
if not TRELLO_CALLBACK_URL:
    raise RuntimeError("TRELLO_CALLBACK_URL not set!")

# ------------------ FastAPI App ------------------
app = FastAPI()

# ------------------ CORS ------------------
origins = [
    FRONTEND_URL,
    "http://localhost:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ------------------ Routers ------------------
from app.routes.fake_webhook import router as fake_webhook_router
from app.routes import auth as auth_router
from app.routes import user as user_router
from app.routes import templates as templates_router
from app.routes import generated_docs as generated_docs_router
from app.routes.trello_webhook import router as trello_webhook_router

app.include_router(fake_webhook_router)
app.include_router(auth_router.router, prefix="/auth")
app.include_router(user_router.router, prefix="/api")
app.include_router(templates_router.router, prefix="/templates", tags=["Templates"])
app.include_router(generated_docs_router.router, prefix="/generated_docs", tags=["GeneratedDocs"])
app.include_router(trello_webhook_router)

# ------------------ Trello Services ------------------
from app.services.trello_service import (
    connect_to_trello,
    save_token,
    get_user_generated_boards,
    get_board_name,
    register_trello_webhook
)
from app.models.user_token_model import get_all_user_tokens, get_user_token, save_user_token
from app.services.workflow_service import execute_workflow

# ------------------ /pm Endpoint for Trello ------------------
@app.head("/pm")
@app.get("/pm")
async def trello_webhook_verify():
    """Trello validation endpoint, always return 200."""
    return Response(content="ok", status_code=200)


@app.post("/pm")
async def trello_webhook_event(request: Request):
    """
    Trello webhook POST endpoint: triggers workflow per board owner.
    """
    payload = await request.json()
    print("📩 Trello webhook received:", payload)

    board_id = payload.get("action", {}).get("data", {}).get("board", {}).get("id")
    if not board_id:
        return {"status": "ignored", "message": "No board ID in webhook"}

    db = app.state.db

    # Lookup the owner of this board
    board_entry = await db["board_user_map"].find_one({"board_id": board_id})
    if not board_entry:
        print(f"⚠️ No user found for board {board_id}")
        return {"status": "error", "message": "User not found for this board"}

    user_id = board_entry["user_id"]

    # Trigger workflow in background
    asyncio.create_task(execute_workflow(user_id, board_id, data={"template": "default"}, db=db))
    print(f"🚀 Workflow triggered for board {board_id}, user {user_id}")

    return {"status": "success", "message": "Workflow triggered"}


# ------------------ MongoDB & Startup ------------------
@app.on_event("startup")
async def startup_all():
    client = motor.motor_asyncio.AsyncIOMotorClient(MONGODB_URI)
    app.state.mongo_client = client
    app.state.db = client[DB_NAME]
    db = app.state.db
    print("✅ Connected to MongoDB Atlas")

    users = await get_all_user_tokens(db)
    if not users:
        print("⚠️ No users found with Trello tokens")
        return

    async with httpx.AsyncClient(timeout=20) as client:
        for user in users:
            user_id = user["user_id"]
            token = user["trello_token"]
            if not token:
                continue

            # Fetch user-specific boards
            try:
                res = await client.get(
                    "https://api.trello.com/1/members/me/boards",
                    params={"key": TRELLO_API_KEY, "token": token, "fields": "id,name", "filter": "open"}
                )
                res.raise_for_status()
                boards = res.json()
            except Exception as e:
                print(f"⚠️ Could not fetch boards for {user_id}: {e}")
                continue

            for board in boards:
                board_id = board.get("id")
                board_name = board.get("name")
                if not board_id:
                    continue

                # Map board to user
                await db["board_user_map"].update_one(
                    {"board_id": board_id},
                    {"$set": {"user_id": user_id, "board_name": board_name}},
                    upsert=True
                )

                # Check if webhook already exists
                try:
                    existing_res = await client.get(
                        f"https://api.trello.com/1/tokens/{token}/webhooks",
                        params={"key": TRELLO_API_KEY}
                    )
                    existing_res.raise_for_status()
                    existing = existing_res.json()
                    if any(
                        w.get("callbackURL") == TRELLO_CALLBACK_URL and w.get("idModel") == board_id
                        for w in existing
                    ):
                        print(f"ℹ️ Webhook already exists for '{board_name}'")
                        continue
                except Exception as e:
                    print(f"⚠️ Could not fetch existing webhooks for '{board_name}': {e}")

                # Register webhook per user per board
                try:
                    await register_trello_webhook(
                        board_id=board_id,
                        callback_url=TRELLO_CALLBACK_URL,
                        token=token,
                        key=TRELLO_API_KEY
                    )
                    print(f"✅ Webhook registered for '{board_name}' ({board_id}) user {user_id}")
                    await asyncio.sleep(0.5)
                except Exception as e:
                    print(f"❌ Failed to register webhook for '{board_name}': {e}")


@app.on_event("shutdown")
async def shutdown_db_client():
    client = getattr(app.state, "mongo_client", None)
    if client:
        client.close()
        print("🛑 MongoDB connection closed")


# ------------------ Trello Endpoints ------------------
@app.get("/trello/connect")
def trello_connect():
    return connect_to_trello()


@app.get("/trello/callback")
def trello_callback():
    return RedirectResponse(f"{FRONTEND_URL}/boards")


@app.post("/trello/save_token")
async def trello_save_token(request: Request):
    """
    Save Trello token for a user and map all boards to that user.
    """
    data = await request.json()
    user_id = data.get("user_id")
    trello_token = data.get("trello_token")
    db = app.state.db
    print("📥 save_token payload:", data)

    if not user_id or not trello_token:
        return {"status": "error", "message": "user_id and trello_token are required"}

    # Save Trello token in MongoDB
    try:
        await save_user_token(user_id, trello_token, db)
        print(f"✅ Trello token saved for user {user_id}")
    except Exception as e:
        print(f"❌ Failed to save Trello token for {user_id}: {e}")
        return {"status": "error", "message": "Failed to save token"}

    # Fetch all boards for this user
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            res = await client.get(
                "https://api.trello.com/1/members/me/boards",
                params={
                    "key": TRELLO_API_KEY,
                    "token": trello_token,
                    "fields": "id,name,desc"
                }
            )
            res.raise_for_status()
            boards = res.json()
            print(f"ℹ️ Fetched {len(boards)} boards for user {user_id}")
    except Exception as e:
        print(f"⚠️ Could not fetch boards for {user_id}: {e}")
        return {"status": "error", "message": "Failed to fetch boards"}

    # Map each board to the user in MongoDB
    mapped_count = 0
    for board in boards:
        try:
            await db["board_user_map"].update_one(
                {"board_id": board["id"]},
                {"$set": {
                    "user_id": user_id,
                    "board_name": board.get("name", ""),
                    "board_desc": board.get("desc", "")
                }},
                upsert=True
            )
            mapped_count += 1
        except Exception as e:
            print(f"⚠️ Failed to map board {board['id']} for {user_id}: {e}")

    return {
        "status": "success",
        "message": f"Trello token saved and {mapped_count} boards mapped to user {user_id}"
    }

# ------------------ Boards with Previous Headings ------------------
@app.get("/trello/boards_with_headings")
async def trello_boards_with_headings(user_id: str):
    """
    Returns all boards belonging to the specific user.
    Marks which boards have generated documents and previous headings.
    """
    db = app.state.db
    token = await get_user_token(user_id, db)
    if not token:
        return {"status": "error", "message": "User not connected to Trello", "boards": []}

    # Fetch all boards for this user via Trello API
    async with httpx.AsyncClient(timeout=15) as client:
        try:
            res = await client.get(
                "https://api.trello.com/1/members/me/boards",
                params={"key": TRELLO_API_KEY, "token": token, "fields": "id,name,desc", "filter": "open"}
            )
            res.raise_for_status()
            boards = res.json()
        except Exception as e:
            return {"status": "error", "message": f"Failed to fetch boards: {e}", "boards": []}

    # Fetch user's generated documents
    docs_cursor = db["generated_docs"].find({"user_id": user_id})
    docs_list = await docs_cursor.to_list(length=None)
    doc_map = {doc["project_id"]: doc for doc in docs_list}

    boards_with_status = []
    for b in boards:
        board_id = b["id"]
        has_doc = board_id in doc_map
        raw_doc = doc_map[board_id].get("generated_docs", "") if has_doc else ""
        previous_headings = re.findall(r'##\s*(.+)', raw_doc, flags=re.IGNORECASE) if has_doc else []

        boards_with_status.append({
            "id": board_id,
            "name": b.get("name", ""),
            "desc": b.get("desc", ""),
            "has_generated_doc": has_doc,
            "previous_headings": previous_headings
        })

    return {"status": "success", "boards": boards_with_status}




# ------------------ Workflow Endpoints ------------------
@app.post("/workflow/run")
async def run_workflow(request: Request):
    data = await request.json()
    user_id = data.get("user_id")
    project_id = data.get("project_id")
    if not user_id or not project_id:
        return {"status": "error", "message": "user_id and project_id are required"}
    return await execute_workflow(user_id, project_id, data, db=app.state.db)


@app.get("/workflow/generated")
async def get_generated_doc(user_id: str, project_id: str, template_name: str):
    db = app.state.db
    collection = db["generated_docs"]
    doc = await collection.find_one({
        "user_id": user_id,
        "project_id": project_id,
        "template_name": template_name
    })
    if not doc:
        return await execute_workflow(user_id, project_id, {"template": template_name}, db=db)

    board_name = doc.get("board_name") or "Unknown Board"
    diagrams = doc.get("generated_diagrams", {})
    for heading, diagram in diagrams.items():
        if "image" in diagram:
            diagram["image"] = f"data:image/png;base64,{diagram['image']}"

    return {
        "status": "success",
        "template_name": template_name,
        "generated_docs": doc.get("generated_docs", ""),
        "generated_diagrams": diagrams,
        "board_name": board_name
    }


# ------------------ Run App ------------------
if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=PORT, reload=True)
