import re
from datetime import datetime

#  ADDED
from app.models.subscription_model import (
    can_generate_doc,
    increment_doc_count,
)


async def save_generated_doc(
    db,
    user_id: str,
    project_id: str,
    template_name: str,
    content: str,
    source: str = "trello",
    team_id: str = None,
    is_final: bool = False,
    workspace_name: str = None
):
    collection = db["generated_docs"]

    # ======================================================
    #  SUBSCRIPTION CHECK
    # ======================================================
    allowed, reason = await can_generate_doc(user_id, db)

    if not allowed:
        raise ValueError(f"SUBSCRIPTION_LIMIT: {reason}")

    # ======================================================
    #  DEDUPLICATE CONTENT BEFORE SAVING
    # ======================================================
    def deduplicate_content(text: str) -> str:
        paragraphs = re.split(r'\n{2,}', text)

        seen = []
        result = []

        for p in paragraphs:
            normalized = re.sub(r'\s+', ' ', p.strip())

            if normalized and normalized not in seen:
                seen.append(normalized)
                result.append(p.strip())

        return '\n\n'.join(result)

    content = deduplicate_content(content)

    # ======================================================
    # ❗ REMOVE OLD "LATEST" FLAGS (workspace-aware)
    # ======================================================
    workspace = await db["workspaces"].find_one(
        {"members": user_id}
    )

    member_ids = []
    workspace_id = None
    workspace_owner_id = None

    if workspace:
        member_ids = workspace.get("members", [])
        workspace_id = str(workspace["_id"])
        workspace_owner_id = workspace["owner_id"]
    else:
        member_ids = [user_id]

    await collection.update_many(
        {
            "workspace_id": workspace_id,
            "project_id": project_id,
            "template_name": template_name
        },
        {
            "$set": {"is_latest": False}
        }
    )

    # ======================================================
    #  GET NEXT VERSION (workspace-wide)
    # ======================================================
    last_doc = await collection.find_one(
        {
            "workspace_id": workspace_id,
            "project_id": project_id,
            "template_name": template_name
        },
        sort=[("version", -1)]
    )

    next_version = (
        last_doc.get("version", 0) + 1
    ) if last_doc else 1

    # ======================================================
    #  INSERT NEW DOCUMENT AS LATEST (SHARED WORKSPACE)
    # ======================================================
    await collection.insert_one({
        "user_id": user_id,  # who generated it
        "workspace_id": workspace_id,
        "workspace_owner_id": workspace_owner_id,

        # 🔥 IMPORTANT: shared visibility field
        "visible_to": member_ids,

        "project_id": project_id,
        "template_name": template_name,
        "generated_docs": content,
        "version": next_version,
        "source": source,
        "team_id": team_id,
        "workspace_name": workspace_name or "Unknown Project",
        "created_at": datetime.utcnow(),
        "is_latest": True,
        "is_final": is_final
    })

    # ======================================================
    #  INCREMENT DOC COUNT (owner billing already handled)
    # ======================================================
    await increment_doc_count(user_id, db)

    print(
        f" Document saved (v{next_version}) "
        f"is_latest=True is_final={is_final}"
    )


# ======================================================
#  SPLIT DOCUMENT INTO SECTIONS
# ======================================================
def split_into_sections(doc: str) -> dict:

    sections = {}
    current_heading = None
    buffer = []

    for line in doc.split("\n"):

        line_strip = line.strip()

        if re.match(r"^#+\s*\d+(\.\d+)*", line_strip):

            if current_heading:
                sections[current_heading] = "\n".join(buffer).strip()
                buffer = []

            current_heading = line_strip

        else:
            buffer.append(line)

    if current_heading:
        sections[current_heading] = "\n".join(buffer).strip()

    return sections