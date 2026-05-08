from app.services.github_code_service import fetch_file
IMPORTANT_FILES = [
    "main.py", "app.py", "index.js", "server.js"
]

IMPORTANT_FOLDERS = [
    "routes", "controllers", "services", "models"
]

IGNORE = [
    "node_modules", "dist", "build", ".env", "__pycache__"
]


def is_important(path: str):
    if any(x in path for x in IGNORE):
        return False

    if any(path.endswith(f) for f in IMPORTANT_FILES):
        return True

    if any(folder in path for folder in IMPORTANT_FOLDERS):
        return True

    if path.endswith(".md") or path.endswith("requirements.txt"):
        return True

    return False

async def build_github_context(token, owner, repo, tree):
    context = []

    for item in tree.get("tree", []):

        if item["type"] != "blob":
            continue

        path = item["path"]

        # ✅ APPLY YOUR FILTER LOGIC
        if not is_important(path):
            continue

        try:
            content = await fetch_file(token, owner, repo, path)

            context.append({
                "path": path,
                "content": content[:4000]  # LLM-safe trim
            })

        except Exception:
            continue

        if len(context) >= 20:
            break

    return context
