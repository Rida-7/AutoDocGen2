import httpx


async def join_channel(token: str, channel_id: str):
    async with httpx.AsyncClient() as client:
        res = await client.post(
            "https://slack.com/api/conversations.join",
            headers={"Authorization": f"Bearer {token}"},
            json={"channel": channel_id}
        )
    return res.json()


async def fetch_messages(token: str, channel_id: str):
    async with httpx.AsyncClient() as client:
        res = await client.get(
            "https://slack.com/api/conversations.history",
            headers={"Authorization": f"Bearer {token}"},
            params={"channel": channel_id, "limit": 100}
        )
    return res.json()
