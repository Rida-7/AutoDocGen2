IMPORTANT_FOLDERS = [
    "routes/",
    "controllers/",
    "services/",
    "models/",
    "api/",
    "auth/",
    "database/",
    "schemas/",
    "core/"
]

IMPORTANT_FILES = [
    "requirements.txt",
    "package.json",
    "docker-compose.yml",
    ".env",
    "main.py",
    "app.py"
]


def is_major_github_change(payload: dict):

    commits = payload.get("commits", [])

    total_files_changed = 0
    important_changes = []

    for commit in commits:

        added = commit.get("added", [])
        modified = commit.get("modified", [])
        removed = commit.get("removed", [])

        changed_files = added + modified + removed

        total_files_changed += len(changed_files)

        for file in changed_files:

            # important folders
            if any(folder in file for folder in IMPORTANT_FOLDERS):
                important_changes.append(file)

            # important files
            if any(file.endswith(f) for f in IMPORTANT_FILES):
                important_changes.append(file)

    # -----------------------------
    # RULES FOR MAJOR CHANGE
    # -----------------------------

    # many files changed
    if total_files_changed >= 8:
        return True, important_changes

    # critical backend/auth/db changes
    if len(important_changes) >= 2:
        return True, important_changes

    return False, important_changes
