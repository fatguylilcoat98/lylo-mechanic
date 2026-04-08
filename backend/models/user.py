"""
LYLO Mechanic — User Model + Check Gating + Monetization
Christopher Hughes · The Good Neighbor Guard
Truth · Safety · We Got Your Back

Pricing:
  FREE  — 5 checks/month, basic diagnosis
  PRO   — $4.99/month, 50 checks, full reports + scam detection
  ADD-ON — +10 checks for $1.99
"""

import os
import time
import json
import hashlib
import threading
from datetime import datetime, timezone
from typing import Optional, Dict, Literal
from collections import defaultdict

# ── In-memory user store (swap for DB in production) ──────────────────────
_users: Dict[str, dict] = {}
_users_lock = threading.Lock()

# ── Plan definitions ──────────────────────────────────────────────────────
PLANS = {
    "free": {
        "name": "Free",
        "checks_per_month": 5,
        "price": 0,
        "features": ["basic_diagnosis", "urgency_level", "basic_explanation"],
    },
    "pro": {
        "name": "LYLO PRO",
        "checks_per_month": 50,
        "price": 4.99,
        "features": [
            "full_diagnosis", "price_range", "scam_detection",
            "repair_confidence", "shop_script", "red_flags",
            "obd_deep_analysis", "priority_processing",
        ],
    },
}

ADDON_CHECKS = 10
ADDON_PRICE = 1.99


# ── User Model ────────────────────────────────────────────────────────────

def _new_user(user_id: str, plan: str = "free") -> dict:
    """Create a new user record."""
    plan_info = PLANS.get(plan, PLANS["free"])
    return {
        "id": user_id,
        "email": "",
        "plan": plan,
        "checks_remaining": plan_info["checks_per_month"],
        "checks_used_total": 0,
        "last_reset": time.time(),
        "created_at": time.time(),
        "stripe_customer_id": None,
        "addons_purchased": 0,
    }


def get_or_create_user(user_id: str) -> dict:
    """Get existing user or create a new free user."""
    with _users_lock:
        if user_id not in _users:
            _users[user_id] = _new_user(user_id)
        return _users[user_id]


def get_user(user_id: str) -> Optional[dict]:
    """Get user without creating."""
    with _users_lock:
        return _users.get(user_id)


def upgrade_user(user_id: str, plan: str = "pro") -> dict:
    """Upgrade user to a paid plan."""
    with _users_lock:
        user = _users.get(user_id)
        if not user:
            user = _new_user(user_id, plan)
            _users[user_id] = user
        else:
            plan_info = PLANS.get(plan, PLANS["pro"])
            user["plan"] = plan
            user["checks_remaining"] = plan_info["checks_per_month"]
            user["last_reset"] = time.time()
        return user


def add_checks(user_id: str, count: int = ADDON_CHECKS) -> dict:
    """Add purchased checks to user."""
    with _users_lock:
        user = _users.get(user_id)
        if user:
            user["checks_remaining"] += count
            user["addons_purchased"] += 1
        return user


# ── Monthly Reset ─────────────────────────────────────────────────────────

def _reset_if_due(user: dict):
    """Reset checks if 30+ days since last reset."""
    elapsed = time.time() - user["last_reset"]
    if elapsed >= 30 * 86400:  # 30 days
        plan_info = PLANS.get(user["plan"], PLANS["free"])
        user["checks_remaining"] = plan_info["checks_per_month"]
        user["last_reset"] = time.time()


# ── Check Gate (Core Money Function) ─────────────────────────────────────

def can_run_check(user_id: str) -> dict:
    """Gate function: can this user run a check?

    Returns: {
        "allowed": bool,
        "checks_remaining": int,
        "plan": str,
        "upgrade_required": bool,
        "message": str
    }
    """
    user = get_or_create_user(user_id)
    _reset_if_due(user)

    if user["checks_remaining"] <= 0:
        if user["plan"] == "free":
            return {
                "allowed": False,
                "checks_remaining": 0,
                "plan": user["plan"],
                "upgrade_required": True,
                "message": "You've used all 5 free checks this month. Upgrade to LYLO PRO for 50 checks/month.",
            }
        else:
            return {
                "allowed": False,
                "checks_remaining": 0,
                "plan": user["plan"],
                "upgrade_required": False,
                "addon_available": True,
                "message": "You've used all 50 PRO checks this month. Add 10 more for $1.99.",
            }

    # Deduct check
    user["checks_remaining"] -= 1
    user["checks_used_total"] += 1

    return {
        "allowed": True,
        "checks_remaining": user["checks_remaining"],
        "plan": user["plan"],
        "upgrade_required": False,
        "message": f"{user['checks_remaining']} checks remaining this month.",
    }


def get_user_status(user_id: str) -> dict:
    """Get user's current check status."""
    user = get_or_create_user(user_id)
    _reset_if_due(user)
    plan_info = PLANS.get(user["plan"], PLANS["free"])
    return {
        "user_id": user_id,
        "plan": user["plan"],
        "plan_name": plan_info["name"],
        "checks_remaining": user["checks_remaining"],
        "checks_per_month": plan_info["checks_per_month"],
        "checks_used_total": user["checks_used_total"],
        "features": plan_info["features"],
        "price": plan_info["price"],
    }


# ── Result Routing (Basic vs Full) ───────────────────────────────────────

def filter_result_by_plan(result: dict, plan: str) -> dict:
    """Filter diagnostic result based on user's plan.

    FREE  → basic fields only (issue, urgency, basic explanation)
    PRO   → full result (price range, scam detection, confidence, etc.)
    """
    if plan == "pro":
        return result  # Full result, nothing stripped

    # FREE tier — strip premium fields
    basic = {}
    for r in result.get("results", []):
        # Keep: code, whats_wrong.summary, urgency
        # Strip: cost, shop_script, red_flags, confidence
        filtered = {
            "code": r.get("code"),
            "whats_wrong": {
                "summary": r.get("whats_wrong", {}).get("summary", ""),
                "explanation": r.get("whats_wrong", {}).get("explanation", ""),
            },
            "urgency": r.get("urgency"),
            "difficulty": {"level": r.get("difficulty", {}).get("level", ""), "label": "Upgrade for full details"},
            "cost": {"note": "Upgrade to LYLO PRO to see price ranges and scam detection"},
            "shop_script": "Upgrade to LYLO PRO for your personalized ShopScript",
            "red_flags": ["Upgrade to LYLO PRO to see red flags and scam alerts"],
            "locked_features": ["price_range", "scam_detection", "shop_script", "red_flags", "confidence"],
        }
        basic.setdefault("results", []).append(filtered)

    basic["input"] = result.get("input")
    basic["input_type"] = result.get("input_type")
    basic["plan"] = "free"
    basic["upgrade_cta"] = {
        "message": "See the full picture — price ranges, scam detection, and your ShopScript",
        "plan": "LYLO PRO",
        "price": "$4.99/month",
        "url": "/api/v1/billing/checkout/pro",
    }
    return basic


# ── Rate Limiting (Anti-Abuse) ────────────────────────────────────────────

_rate_limits: Dict[str, float] = {}
_rate_lock = threading.Lock()
RATE_LIMIT_SECONDS = 20  # 20 second cooldown per IP


def check_rate_limit(ip: str) -> bool:
    """Returns True if request is allowed, False if rate-limited."""
    with _rate_lock:
        now = time.time()
        last = _rate_limits.get(ip, 0)
        if now - last < RATE_LIMIT_SECONDS:
            return False
        _rate_limits[ip] = now
        # Clean old entries (every 100 checks)
        if len(_rate_limits) > 1000:
            cutoff = now - RATE_LIMIT_SECONDS * 2
            _rate_limits.clear()
        return True


# ── Analytics Tracking ────────────────────────────────────────────────────

_events: list = []
_events_lock = threading.Lock()
_events_max = 10000


def log_event(event_type: str, user_id: str = "", details: dict = None):
    """Log an analytics event."""
    with _events_lock:
        _events.append({
            "event": event_type,
            "user_id": user_id,
            "timestamp": time.time(),
            "details": details or {},
        })
        if len(_events) > _events_max:
            _events[:] = _events[-int(_events_max * 0.9):]


def get_analytics_summary() -> dict:
    """Get analytics summary for dashboard."""
    with _events_lock:
        total = len(_events)
        checks = sum(1 for e in _events if e["event"] == "check_used")
        upgrades_clicked = sum(1 for e in _events if e["event"] == "upgrade_clicked")
        upgrades_completed = sum(1 for e in _events if e["event"] == "upgrade_completed")
        return {
            "total_events": total,
            "checks_used": checks,
            "upgrade_clicks": upgrades_clicked,
            "upgrades_completed": upgrades_completed,
            "conversion_rate": round(upgrades_completed / max(upgrades_clicked, 1) * 100, 1),
        }
