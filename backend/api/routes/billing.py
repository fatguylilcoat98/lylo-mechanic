"""
LYLO Mechanic — Billing & Subscription Routes
Christopher Hughes · The Good Neighbor Guard
Truth · Safety · We Got Your Back

Stripe integration for PRO subscriptions and add-on check packs.
"""

import os
from flask import Blueprint, request, jsonify, redirect
from models.user import (
    get_user_status, upgrade_user, add_checks, log_event,
    get_analytics_summary, PLANS, ADDON_CHECKS, ADDON_PRICE,
)

billing_bp = Blueprint("billing", __name__)


# ── Pricing Info ──────────────────────────────────────────────────────────

@billing_bp.route("/plans", methods=["GET"])
def get_plans():
    """Return available plans and pricing."""
    return jsonify({
        "plans": {
            "free": {**PLANS["free"], "cta": "Current Plan"},
            "pro": {**PLANS["pro"], "cta": "Upgrade Now"},
        },
        "addons": {
            "extra_checks": {
                "count": ADDON_CHECKS,
                "price": ADDON_PRICE,
                "description": f"+{ADDON_CHECKS} diagnostic checks",
            },
        },
    })


# ── Stripe Checkout ───────────────────────────────────────────────────────

@billing_bp.route("/checkout/pro", methods=["GET"])
def checkout_pro():
    """Redirect to Stripe checkout for PRO subscription."""
    user_id = request.args.get("user_id", request.remote_addr)
    log_event("upgrade_clicked", user_id)

    stripe_link = os.environ.get("STRIPE_LINK_PRO")
    if not stripe_link:
        return jsonify({
            "error": "Stripe not configured",
            "message": "Payment processing is being set up. Check back soon.",
        }), 503

    return redirect(stripe_link)


@billing_bp.route("/checkout/addon", methods=["GET"])
def checkout_addon():
    """Redirect to Stripe checkout for add-on check pack."""
    user_id = request.args.get("user_id", request.remote_addr)
    log_event("addon_clicked", user_id)

    stripe_link = os.environ.get("STRIPE_LINK_ADDON")
    if not stripe_link:
        return jsonify({
            "error": "Stripe not configured",
            "message": "Payment processing is being set up. Check back soon.",
        }), 503

    return redirect(stripe_link)


# ── Stripe Webhook (handles payment confirmation) ─────────────────────────

@billing_bp.route("/webhook", methods=["POST"])
def stripe_webhook():
    """Handle Stripe webhook events.

    Events:
      checkout.session.completed → upgrade user or add checks
      customer.subscription.deleted → downgrade to free
    """
    import json
    payload = request.get_data(as_text=True)

    # In production, verify Stripe signature here
    # sig = request.headers.get("Stripe-Signature")
    # stripe.Webhook.construct_event(payload, sig, webhook_secret)

    try:
        event = json.loads(payload)
    except Exception:
        return jsonify({"error": "Invalid payload"}), 400

    event_type = event.get("type", "")

    if event_type == "checkout.session.completed":
        session = event.get("data", {}).get("object", {})
        customer_email = session.get("customer_email", "")
        # Determine if PRO or addon by metadata or price
        metadata = session.get("metadata", {})
        purchase_type = metadata.get("type", "pro")

        if purchase_type == "addon":
            user = add_checks(customer_email, ADDON_CHECKS)
            log_event("addon_completed", customer_email)
        else:
            user = upgrade_user(customer_email, "pro")
            log_event("upgrade_completed", customer_email)

        return jsonify({"status": "ok"}), 200

    if event_type == "customer.subscription.deleted":
        session = event.get("data", {}).get("object", {})
        customer_email = session.get("customer_email", "")
        # Downgrade to free (keep remaining checks until month end)
        from models.user import get_or_create_user
        user = get_or_create_user(customer_email)
        user["plan"] = "free"
        log_event("subscription_cancelled", customer_email)
        return jsonify({"status": "ok"}), 200

    return jsonify({"status": "ignored"}), 200


# ── User Status ───────────────────────────────────────────────────────────

@billing_bp.route("/status", methods=["GET"])
def user_status():
    """Get current user's plan and check status."""
    user_id = request.args.get("user_id", request.remote_addr)
    return jsonify(get_user_status(user_id))


# ── Analytics (Admin) ─────────────────────────────────────────────────────

@billing_bp.route("/analytics", methods=["GET"])
def analytics():
    """Analytics summary — admin only in production."""
    return jsonify(get_analytics_summary())


# ── Upgrade Screen Data ───────────────────────────────────────────────────

@billing_bp.route("/upgrade", methods=["GET"])
def upgrade_screen():
    """Return upgrade screen content for the mobile app."""
    return jsonify({
        "headline": "You've used all your free checks",
        "subhead": "Before you approve your next repair:",
        "benefits": [
            "See real price ranges — know what you should pay",
            "Know if you're being upsold or scammed",
            "Get your personalized ShopScript to say at the shop",
            "Red flag alerts — things to watch out for",
            "50 checks per month — 10x more than free",
        ],
        "cta": {
            "text": "Upgrade to LYLO PRO",
            "price": "$4.99/month",
            "url": "/api/v1/billing/checkout/pro",
        },
        "addon": {
            "text": "Just need a few more?",
            "detail": f"+{ADDON_CHECKS} checks for ${ADDON_PRICE}",
            "url": "/api/v1/billing/checkout/addon",
        },
    })
