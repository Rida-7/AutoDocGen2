from datetime import datetime


def get_notification_collection(db):
    return db["notifications"]


async def save_notification(
    db,
    user_id,
    source,
    message,
    project_id
):

    col = get_notification_collection(db)

    await col.insert_one({
        "user_id": user_id,
        "source": source,
        "message": message,
        "project_id": project_id,
        "read": False,
        "created_at": datetime.utcnow()
    })
