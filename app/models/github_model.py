from datetime import datetime

def get_github_token_collection(db):
    return db["github_tokens"]


def get_github_repo_collection(db):
    return db["github_repos"]


async def save_github_token(db, user_id, token_data):
    col = get_github_token_collection(db)

    await col.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "access_token": token_data["access_token"],
                "scope": token_data.get("scope"),
                "token_type": token_data.get("token_type"),
                "updated_at": datetime.utcnow()
            }
        },
        upsert=True
    )


async def get_github_token(db, user_id):
    col = get_github_token_collection(db)
    return await col.find_one({"user_id": user_id})


async def save_github_repo(db, user_id, repo):

    if not isinstance(repo, dict):
        raise ValueError("Repo must be a dictionary")

    owner = repo.get("owner", {})
    if isinstance(owner, str):
        owner = {"login": owner}

    col = get_github_repo_collection(db)

    # 🚨 IMPORTANT FIX: DELETE OLD REPOS FIRST
    await col.delete_many({"user_id": user_id})

    await col.insert_one({
        "user_id": user_id,
        "repo_id": repo.get("id"),
        "repo_name": repo.get("name"),
        "repo_full_name": repo.get("full_name"),
        "repo_owner": owner.get("login"),
        "default_branch": repo.get("default_branch", "main"),
        "updated_at": datetime.utcnow()
    })

async def get_user_repos(db, user_id):
    col = get_github_repo_collection(db)

    repos = []
    cursor = col.find({"user_id": user_id})

    async for r in cursor:
        repos.append(r)

    return repos

def get_github_webhook_collection(db):
    return db["github_webhooks"]


async def save_github_webhook(
    db,
    user_id,
    repo_id,
    webhook_data
):
    col = get_github_webhook_collection(db)

    await col.update_one(
        {
            "user_id": user_id,
            "repo_id": repo_id
        },
        {
            "$set": {
                "webhook_id": webhook_data["id"],
                "webhook_url": webhook_data["config"]["url"],
                "updated_at": datetime.utcnow()
            }
        },
        upsert=True
    )
