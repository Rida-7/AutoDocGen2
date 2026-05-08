from datetime import datetime


# -----------------------------
# SAVE SLACK TOKEN
# -----------------------------
async def save_slack_token(user_id: str, team_id: str, access_token: str, db):

    await db["slack_connections"].update_one(
        {
            "user_id": str(user_id),
            "team_id": str(team_id)
        },
        {
            "$set": {
                "user_id": str(user_id),
                "team_id": str(team_id),
                "access_token": access_token,
                "connected_at": datetime.utcnow()
            }
        },
        upsert=True
    )


# -----------------------------
# GET SLACK TOKEN (IMPROVED)
# -----------------------------
async def get_slack_token(user_id: str, team_id: str, db):
    doc = await db["slack_connections"].find_one({
        "user_id": str(user_id),
        "team_id": str(team_id)
    })

    if not doc:
        return None

    return doc.get("access_token")
