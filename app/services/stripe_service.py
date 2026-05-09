import stripe
import os

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")


def create_checkout_session(user_id: str, plan: str):
    price_map = {
        "starter": 900,  # $9.00 in cents
        "pro": 2900,
        "team": 4900,
    }

    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[
            {
                "price_data": {
                    "currency": "usd",
                    "product_data": {
                        "name": f"{plan.upper()} Plan - AutoDocGen",
                    },
                    "unit_amount": price_map.get(plan, 900),
                },
                "quantity": 1,
            }
        ],
        mode="payment",
        success_url="http://localhost:5173/payment-success?session_id={CHECKOUT_SESSION_ID}",
        cancel_url="http://localhost:5173/pricing",
        metadata={
            "user_id": user_id,
            "plan": plan,
        },
    )

    return session
