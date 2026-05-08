from fastapi import APIRouter, Request, Query
from fastapi.responses import JSONResponse

router = APIRouter()

@router.get("/headings")
async def get_headings(request: Request, template: str = Query(...)):
    db = request.app.state.db.get_collection("templates")
    
    # Case-insensitive search
    import re
    doc = await db.find_one({"template_name": re.compile(f"^{template.strip()}$", re.IGNORECASE)})

    if not doc:
        return JSONResponse(
            status_code=404,
            content={"status": "error", "message": f"No data found for template '{template}'"}
        )

    # Build response dynamically based on template type
    template_type = doc.get("type", "").lower()
    response = {
        "status": "success",
        "template_name": doc.get("template_name"),
        "type": template_type,
    }

    if template_type in ["section", "hierarchical"]:
        response["sections"] = doc.get("sections") or doc.get("structure") or []
    elif template_type == "table":
        response["project_fields"] = doc.get("project_fields")
        response["table_columns"] = doc.get("table_columns", [])
    else:
        response["data"] = doc  # fallback, return the raw document

    return response


@router.get("/list")
async def list_templates(request: Request):
    """
    Return all templates, regardless of source.
    """
    db = request.app.state.db.get_collection("templates")

    # Fetch all templates without filtering by source
    templates = await db.find({}).to_list(None)

    if not templates:
        return {
            "status": "error",
            "templates": [],
            "message": "No templates found"
        }

    result = []
    for t in templates:
        result.append({
            "name": t.get("template_name"),
            "key": t.get("template_key", t.get("template_name")),
            "description": t.get("description", ""),
            "type": t.get("type", ""),
            "source": t.get("source", "general")  # optional: keep source info
        })

    return {
        "status": "success",
        "templates": result
    }
