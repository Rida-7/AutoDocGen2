from fastapi import APIRouter, HTTPException, Request
from bson import ObjectId

router = APIRouter()

@router.get("/all")
async def get_all_generated_docs(request: Request, user_id: str):
    """
    Fetch all generated documents for a specific user.
    """
    db = request.app.state.db
    collection = db["generated_docs"]

    docs_cursor = collection.find({"user_id": user_id})
    docs = []
    async for doc in docs_cursor:
        docs.append({
            "id": str(doc.get("_id", "")),
            "project_id": doc.get("project_id"),
            "template_name": doc.get("template_name"),
            "generated_docs": doc.get("generated_docs", ""),
            "board_name": doc.get("board_name", "Unknown Board"),  # <-- add this
            "created_at": str(doc.get("created_at", "")),
        })

    if not docs:
        raise HTTPException(status_code=404, detail="No generated documents found")

    return {"status": "success", "count": len(docs), "documents": docs}
