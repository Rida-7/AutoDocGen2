import httpx
from app.models.slack_model import get_slack_token


async def get_channel_name(token: str, channel_id: str):
    async with httpx.AsyncClient() as client:
        res = await client.get(
            "https://slack.com/api/conversations.info",
            headers={"Authorization": f"Bearer {token}"},
            params={"channel": channel_id}
        )
        data = res.json()

        if not data.get("ok"):
            return "Unknown Channel"

        return data["channel"]["name"]


async def join_channel(token: str, channel_id: str):
    async with httpx.AsyncClient() as client:
        res = await client.post(
            "https://slack.com/api/conversations.join",
            headers={"Authorization": f"Bearer {token}"},
            json={"channel": channel_id}
        )
    return res.json()


async def fetch_channel_messages(token: str, channel_id: str):
    async with httpx.AsyncClient() as client:
        res = await client.get(
            "https://slack.com/api/conversations.history",
            headers={"Authorization": f"Bearer {token}"},
            params={"channel": channel_id, "limit": 100}
        )
        return res.json()


async def fetch_channels(token: str):
    async with httpx.AsyncClient() as client:
        res = await client.get(
            "https://slack.com/api/conversations.list",
            headers={"Authorization": f"Bearer {token}"},
            params={
                "limit": 200,
                "types": "public_channel,private_channel"
            }
        )
        data = res.json()
        print("🔥 SLACK RESPONSE:", data)
        return data
        
async def run_slack_workflow(user_id: str, team_id: str, channel_id: str, db):

    token = await get_slack_token(user_id, team_id, db)

    print("🧪 SLACK WORKFLOW START")
    print("USER:", user_id)
    print("TEAM:", team_id)
    print("CHANNEL:", channel_id)

    if not token:
        return {
            "status": "error",
            "message": "Slack token not found"
        }

    # Step 1: Fetch messages
    res = await fetch_channel_messages(token, channel_id)

    # Step 2: Join if not in channel
    if res.get("error") == "not_in_channel":
        join_res = await join_channel(token, channel_id)

        if not join_res.get("ok"):
            return {
                "status": "error",
                "message": "Bot failed to join channel",
                "debug": join_res
            }

        res = await fetch_channel_messages(token, channel_id)

    # Step 3: Final validation
    if not res.get("ok"):
        return {
            "status": "error",
            "message": res.get("error", "fetch failed"),
            "debug": res
        }

    messages = res.get("messages", [])

    conversation = "\n".join(
        f"{m.get('user', 'unknown')}: {m.get('text', '')}"
        for m in messages if m.get("text")
    )

    return {
        "status": "success",
        "source": "slack",
        "channel_id": channel_id,
        "conversation": conversation,
        "messages": messages
    }

