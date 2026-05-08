import re
from datetime import datetime


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
    # ✅ DEDUPLICATE CONTENT BEFORE SAVING
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
    # ❗ REMOVE OLD "LATEST" FLAGS
    # ======================================================
    await collection.update_many(
        {
            "user_id": user_id,
            "project_id": project_id,
            "template_name": template_name
        },
        {"$set": {"is_latest": False}}
    )

    # ======================================================
    # 🔢 GET NEXT VERSION
    # ======================================================
    last_doc = await collection.find_one(
        {
            "user_id": user_id,
            "project_id": project_id,
            "template_name": template_name
        },
        sort=[("version", -1)]
    )
    next_version = (last_doc.get("version", 0) + 1) if last_doc else 1

    # ======================================================
    # 💾 INSERT NEW DOCUMENT AS LATEST
    # ======================================================
    await collection.insert_one({
        "user_id": user_id,
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

    print(f"✅ Document saved (v{next_version}) is_latest=True is_final={is_final}")


# ======================================================
# 🧩 SPLIT DOCUMENT INTO SECTIONS
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
