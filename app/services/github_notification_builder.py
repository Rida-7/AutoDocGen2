def build_github_message(payload: dict, important_changes: list):

    repo = payload["repository"]["full_name"]

    commits = payload.get("commits", [])
    commit_count = len(commits)

    pusher = payload.get("pusher", {}).get("name", "Someone")

    # -----------------------------------
    # Important changed files
    # -----------------------------------
    files_text = ""

    for file in important_changes[:5]:
        files_text += f"\n• {file}"

    # -----------------------------------
    # Final notification message
    # -----------------------------------
    return (
        f"🔥 Major GitHub update in '{repo}'\n\n"
        f"👤 By: {pusher}\n"
        f"📝 Commits: {commit_count}\n"
        f"📂 Important changes:{files_text}"
    )
