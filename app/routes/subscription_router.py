from fastapi import APIRouter, Request, HTTPException
from app.models.subscription_model import (
    get_user_subscription,
    upgrade_plan,
    PLAN_LIMITS,
    PlanType
)
from app.services.stripe_service import create_checkout_session
import stripe

router = APIRouter(prefix="/subscription", tags=["Subscription"])
endpoint_secret = "whsec_a3AzLDHltfilLI3RheKhMY3K73RBcIfZ"


@router.get("/status")
async def get_status(user_id: str, request: Request):
    db = request.app.state.db
    sub = await get_user_subscription(user_id, db)
    plan = sub.get("plan", PlanType.FREE)
    limit = PLAN_LIMITS.get(plan, PLAN_LIMITS[PlanType.FREE])
    docs_used = sub.get("docs_used", 0)
    docs_limit = limit["docs"]

    return {
        "plan": plan,
        "docs_used": docs_used,
        "docs_limit": docs_limit,
        "unlimited": docs_limit == -1,
        "period_end": sub.get("period_end"),
    }


@router.get("/plans")
async def get_plans():
    return {
        "plans": [
            {"key": "free",    "name": "Free",    "price": 0,  "docs": 10,  "period": "lifetime"},
            {"key": "starter", "name": "Starter", "price": 9,  "docs": 50,  "period": "monthly"},
            {"key": "pro",     "name": "Pro",     "price": 29, "docs": -1,  "period": "monthly"},
            {"key": "team",    "name": "Team",    "price": 49, "docs": -1,  "period": "monthly"},
        ]
    }


@router.post("/upgrade")
async def upgrade(request: Request, payload: dict):
    db = request.app.state.db
    user_id = payload.get("user_id")
    new_plan = payload.get("plan")

    if not user_id or not new_plan:
        raise HTTPException(status_code=400, detail="Missing user_id or plan")

    if new_plan not in [p.value for p in PlanType]:
        raise HTTPException(status_code=400, detail="Invalid plan")

    await upgrade_plan(user_id, new_plan, db)

    return {"status": "upgraded", "plan": new_plan}

@router.post("/create-checkout-session")
async def create_checkout(request: Request, payload: dict):
    user_id = payload.get("user_id")
    plan = payload.get("plan")

    if not user_id or not plan:
        raise HTTPException(status_code=400, detail="Missing data")

    session = create_checkout_session(user_id, plan)

    return {
        "url": session.url
    }

@router.post("/create-payment-intent")
async def create_payment_intent(data: dict):
    try:
        plan = data.get("plan")

        amount_map = {
            "starter": 900,
            "pro": 2900,
            "team": 4900
        }

        amount = amount_map.get(plan, 900)

        intent = stripe.PaymentIntent.create(
            amount=amount,
            currency="usd",
            automatic_payment_methods={"enabled": True},
            metadata={
                "user_id": data.get("user_id"),
                "plan": plan
    }
)

        return {
            "clientSecret": intent.client_secret
        }

    except Exception as e:
        print("Stripe error:", str(e))
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/stripe-webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, endpoint_secret
        )

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    # PAYMENT SUCCESS EVENT
    if event["type"] == "payment_intent.succeeded":
        payment = event["data"]["object"]

        # extract metadata
        user_id = payment["metadata"]["user_id"]
        plan = payment["metadata"]["plan"]

        # update DB here
        await upgrade_plan(user_id, plan, request.app.state.db)

    return {"status": "success"}
