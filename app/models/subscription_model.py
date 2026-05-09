from datetime import datetime, timedelta
from enum import Enum


class PlanType(str, Enum):
    FREE = "free"
    STARTER = "starter"
    PRO = "pro"
    TEAM = "team"


PLAN_LIMITS = {
    PlanType.FREE:    {"docs": 10, "monthly": False, "price": 0},
    PlanType.STARTER: {"docs": 50, "monthly": True, "price": 9},
    PlanType.PRO:     {"docs": -1, "monthly": True, "price": 29},  # -1 = unlimited
    PlanType.TEAM:    {"docs": -1, "monthly": True, "price": 49},
}


async def get_user_subscription(user_id: str, db) -> dict:
    sub = await db["subscriptions"].find_one({"user_id": user_id})

    if not sub:
        # Auto-create free plan on first check
        sub = {
            "user_id": user_id,
            "plan": PlanType.FREE,
            "docs_used": 0,
            "period_start": datetime.utcnow(),
            "period_end": None,
            "is_active": True,
            "created_at": datetime.utcnow()
        }

        await db["subscriptions"].insert_one(sub)

    return sub


async def can_generate_doc(user_id: str, db) -> tuple[bool, str]:
    """
    Returns:
        (allowed: bool, reason: str)
    """

    # =========================================
    # TEAM / WORKSPACE BILLING SUPPORT
    # =========================================
    # If user is a workspace member,
    # consume owner's subscription quota
    workspace = await db["workspaces"].find_one(
        {"members": user_id}
    )

    if workspace and workspace["owner_id"] != user_id:
        billing_user_id = workspace["owner_id"]
    else:
        billing_user_id = user_id

    sub = await get_user_subscription(
        billing_user_id,
        db
    )

    plan = sub.get("plan", PlanType.FREE)

    limit = PLAN_LIMITS.get(
        plan,
        PLAN_LIMITS[PlanType.FREE]
    )

    # =========================================
    # UNLIMITED PLAN
    # =========================================
    if limit["docs"] == -1:
        return True, "ok"

    # =========================================
    # MONTHLY RESET
    # =========================================
    if limit["monthly"] and sub.get("period_end"):

        if datetime.utcnow() > sub["period_end"]:

            await db["subscriptions"].update_one(
                {"user_id": billing_user_id},
                {
                    "$set": {
                        "docs_used": 0,
                        "period_start": datetime.utcnow(),
                        "period_end": (
                            datetime.utcnow() +
                            timedelta(days=30)
                        )
                    }
                }
            )

            return True, "ok"

    docs_used = sub.get("docs_used", 0)

    # =========================================
    # LIMIT CHECK
    # =========================================
    if docs_used >= limit["docs"]:

        return (
            False,
            f"Limit reached. You've used "
            f"{docs_used}/{limit['docs']} docs "
            f"on the {plan} plan. "
            f"Upgrade to generate more."
        )

    return True, "ok"


async def increment_doc_count(user_id: str, db):

    # =========================================
    # TEAM / WORKSPACE BILLING SUPPORT
    # =========================================
    workspace = await db["workspaces"].find_one(
        {"members": user_id}
    )

    billing_user_id = (
        workspace["owner_id"]
        if workspace and workspace["owner_id"] != user_id
        else user_id
    )

    await db["subscriptions"].update_one(
        {"user_id": billing_user_id},
        {"$inc": {"docs_used": 1}}
    )


async def upgrade_plan(
    user_id: str,
    new_plan: str,
    db
):

    limit = PLAN_LIMITS.get(
        new_plan,
        PLAN_LIMITS[PlanType.FREE]
    )

    update = {
        "plan": new_plan,
        "docs_used": 0,
        "period_start": datetime.utcnow(),
        "is_active": True
    }

    # =========================================
    # MONTHLY PLANS
    # =========================================
    if limit["monthly"]:

        update["period_end"] = (
            datetime.utcnow() +
            timedelta(days=30)
        )

    else:
        update["period_end"] = None

    await db["subscriptions"].update_one(
        {"user_id": user_id},
        {"$set": update},
        upsert=True
    )
