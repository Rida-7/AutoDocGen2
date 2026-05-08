#github_code_service.py
import httpx

GITHUB_API = "https://api.github.com"


async def fetch_repo_tree(token, owner, repo):
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json"
    }

    url = f"{GITHUB_API}/repos/{owner}/{repo}/git/trees/main?recursive=1"

    async with httpx.AsyncClient() as client:
        res = await client.get(url, headers=headers)

    return res.json()


async def fetch_file(token, owner, repo, path):
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json"
    }

    url = f"{GITHUB_API}/repos/{owner}/{repo}/contents/{path}"

    async with httpx.AsyncClient() as client:
        res = await client.get(url, headers=headers)

    data = res.json()

    if isinstance(data, dict) and "content" in data:
        import base64
        return base64.b64decode(data["content"]).decode("utf-8")

    return ""
