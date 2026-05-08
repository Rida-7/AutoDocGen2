import httpx
import os

# --------------------------------------------------
# Resolve board name → board ID (SYNC VERSION)
# --------------------------------------------------
def get_board_id_from_name(
    trello_key: str,
    trello_token: str,
    board_name: str
) -> str:

    if not board_name or board_name == "undefined":
        raise ValueError("Board name is empty or undefined")

    url = "https://api.trello.com/1/members/me/boards"
    params = {
        "key": trello_key,
        "token": trello_token,
        "fields": "id,name"
    }

    with httpx.Client(timeout=30) as client:
        res = client.get(url, params=params)

    if res.status_code != 200:
        raise ValueError(f"Trello API error {res.status_code}: {res.text}")

    for board in res.json():
        if board["name"].strip().lower() == board_name.strip().lower():
            return board["id"]

    raise ValueError(f"No Trello board found with name '{board_name}'")


# --------------------------------------------------
# PM Agent Node (FULLY SYNC SAFE)
# --------------------------------------------------
def fetch_pm_data_node(state: dict) -> dict:

    pm_data = state.get("pm_data") or {}
    source = (
        pm_data.get("source")
        or state.get("source")
        or "trello"
    )

    pm_data["source"] = source
    state["pm_data"] = pm_data

    # ==========================================================
    # 🔥 HARD SAFETY
    # ==========================================================
    if not source:
        raise ValueError("pm_data.source is missing (must be 'slack' or 'trello')")

    # ==========================================================
    # 🔵 SLACK FLOW
    # ==========================================================
    if source == "slack":
        print("✅ Slack detected → bypassing Trello completely")
        state["pm_data"] = pm_data
        return state

    # ==========================================================
    # 🟢 GITHUB FLOW (NEW FIX)
    # ==========================================================
    if source == "github":
        print("✅ GitHub detected → bypassing Trello completely")

        # GitHub already handled upstream in build_state
        # so we just pass state forward safely
        state["pm_data"] = pm_data
        return state

    # ==========================================================
    # 🟡 TRELLO FLOW
    # ==========================================================
    if source != "trello":
        raise ValueError(f"Unknown source: {source}")

    trello_key = state.get("user_trello_key") or os.getenv("TRELLO_API_KEY")
    trello_token = state.get("user_trello_token") or os.getenv("TRELLO_TOKEN")

    project_id = (
    state.get("project_id")
    or (state.get("pm_data") or {}).get("project_id")
    or (state.get("pm_data") or {}).get("board_id")
    or (state.get("pm_data") or {}).get("channel_id")
    or (state.get("pm_data") or {}).get("repo_id")
)

    project_name = state.get("project_name")

    if not trello_key:
        raise ValueError("TRELLO_API_KEY missing in workflow state")

    if not trello_token:
        raise ValueError("Trello token missing in workflow state")

    if not project_id and not project_name:
        project_id = (
            state.get("pm_data", {}).get("channel_id")
            or state.get("pm_data", {}).get("board_id")
        )

    if not project_id and not project_name:
        raise ValueError(
            "Both project_id and project_name are missing even after recovery"
        )

    # --------------------------------------------------
    # Fetch Trello cards (SYNC)
    # --------------------------------------------------
    url = f"https://api.trello.com/1/boards/{project_id}/cards"
    params = {
        "key": trello_key,
        "token": trello_token,
        "fields": "id,name,desc,idList"
    }

    with httpx.Client(timeout=30) as client:
        res = client.get(url, params=params)

    if res.status_code != 200:
        raise ValueError(f"Trello cards fetch failed: {res.text}")

    state["pm_data"] = {
        "source": "trello",
        "board_id": project_id,
        "cards": res.json()
    }

    return state
