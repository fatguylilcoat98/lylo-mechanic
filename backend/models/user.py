"""
LYLO Mechanic — User Model + Check Gating + Monetization
The Good Neighbor Guard · Built by Christopher Hughes · Sacramento, CA
Created with the help of AI collaborators (Claude · GPT · Gemini · Groq)
Truth · Safety · We Got Your Back

Pricing:
  FREE   — 5 checks/month, basic diagnosis
  PRO    — $4.99/month, 50 checks, full reports + scam detection
  ADD-ON — +10 checks for $1.99
"""

import os
import time
import threading
from datetime import datetime, timezone
from typing import Optional, Dict

from sqlalchemy import (
    create_engine, Column, String, Integer, Float,
    Boolean, Text, BigInteger
)
from sqlalchemy.orm import declarative_base, sessionmaker, scoped_session

# ── Database Setup ────────────────────────────────────────────────────────

DATABASE_URL = os.getenv("DATABASE_URL", "")

# Render gives postgres:// URLs but SQLAlchemy needs postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+pg8000://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+pg8000://", 1)
  
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is not set.")

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = scoped_session(sessionmaker(bind=engine))
Base = declarative_base()


# ── ORM Models ────────────────────────────────────────────────────────────

class UserRecord(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, index=True)
    email = Column(String, default="")
    plan = Column(String, default="free")
    checks_remaining = Column(Integer, default=5)
    checks_used_total = Column(Integer, default=0)
    last_reset = Column(Float, default=time.time)
    created_at = Column(Float, default=time.time)
    stripe_customer_id = Column(String, nullable=True)
    addons_purchased = Column(Integer, default=0)


class AnalyticsEvent(Base):
    __tablename__ = "analytics_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event = Column(String, index=True)
    user_id = Column(String, default="")
    timestamp = Column(Float, default=time.time)
    details = Column(Text, default="{}")


class RateLimit(Base):
    __tablename__ = "rate_limits"

    ip = Column(String, primary_key=True)
    last_request = Column(Float, default=time.time)


def init_db():
    """Create all tables if they don't exist."""
    Base.metadata.create_all(bind=engine)


# Initialize tables on import
init_db()


# ── Plan Definitions ──────────────────────────────────────────────────────

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
RATE_LIMIT_SECONDS = 20


# ── Helpers ───────────────────────────────────────────────────────────────

def _reset_if_due(user: UserRecord, db):
    """Reset checks if 30+ days since last reset."""
    elapsed = time.time() - user.last_reset
    if elapsed >= 30 * 86400:
        plan_info = PLANS.get(user.plan, PLANS["free"])
        user.checks_remaining = plan_info["checks_per_month"]
        user.last_reset = time.time()
        db.commit()


def _user_to_dict(user: UserRecord) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "plan": user.plan,
        "checks_remaining": user.checks_remaining,
        "checks_used_total": user.checks_used_total,
        "last_reset": user.last_reset,
        "created_at": user.created_at,
        "stripe_customer_id": user.stripe_customer_id,
        "addons_purchased": user.addons_purchased,
    }


# ── User CRUD ─────────────────────────────────────────────────────────────

def get_or_create_user(user_id: str) -> dict:
    """Get existing user or create a new free user."""
    db = SessionLocal()
    try:
        user = db.query(UserRecord).filter(UserRecord.id == user_id).first()
        if not user:
            plan_info = PLANS["free"]
            user = UserRecord(
                id=user_id,
                plan="free",
                checks_remaining=plan_info["checks_per_month"],
                checks_used_total=0,
                last_reset=time.time(),
                created_at=time.time(),
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        return _user_to_dict(user)
    finally:
        db.close()


def get_user(user_id: str) -> Optional[dict]:
    """Get user without creating."""
    db = SessionLocal()
    try:
        user = db.query(UserRecord).filter(UserRecord.id == user_id).first()
        return _user_to_dict(user) if user else None
    finally:
        db.close()


def upgrade_user(user_id: str, plan: str = "pro") -> dict:
    """Upgrade user to a paid plan."""
    db = SessionLocal()
    try:
        user = db.query(UserRecord).filter(UserRecord.id == user_id).first()
        plan_info = PLANS.get(plan, PLANS["pro"])
        if not user:
            user = UserRecord(
                id=user_id,
                plan=plan,
                checks_remaining=plan_info["checks_per_month"],
                last_reset=time.time(),
                created_at=time.time(),
            )
            db.add(user)
        else:
            user.plan = plan
            user.checks_remaining = plan_info["checks_per_month"]
            user.last_reset = time.time()
        db.commit()
        db.refresh(user)
        return _user_to_dict(user)
    finally:
        db.close()


def add_checks(user_id: str, count: int = ADDON_CHECKS) -> Optional[dict]:
    """Add purchased checks to user."""
    db = SessionLocal()
    try:
        user = db.query(UserRecord).filter(UserRecord.id == user_id).first()
        if user:
            user.checks_remaining += count
            user.addons_purchased += 1
            db.commit()
            db.refresh(user)
            return _user_to_dict(user)
        return None
    finally:
        db.close()


# ── Check Gate ────────────────────────────────────────────────────────────

def can_run_check(user_id: str) -> dict:
    """Gate function: can this user run a check?"""
    db = SessionLocal()
    try:
        user = db.query(UserRecord).filter(UserRecord.id == user_id).first()
        if not user:
            plan_info = PLANS["free"]
            user = UserRecord(
                id=user_id,
                plan="free",
                checks_remaining=plan_info["checks_per_month"],
                checks_used_total=0,
                last_reset=time.time(),
                created_at=time.time(),
            )
            db.add(user)
            db.commit()
            db.refresh(user)

        _reset_if_due(user, db)

        if user.checks_remaining <= 0:
            if user.plan == "free":
                return {
                    "allowed": False,
                    "checks_remaining": 0,
                    "plan": user.plan,
                    "upgrade_required": True,
                    "message": "You've used all 5 free checks this month. Upgrade to LYLO PRO for 50 checks/month.",
                }
            else:
                return {
                    "allowed": False,
                    "checks_remaining": 0,
                    "plan": user.plan,
                    "upgrade_required": False,
                    "addon_available": True,
                    "message": "You've used all 50 PRO checks this month. Add 10 more for $1.99.",
                }

        user.checks_remaining -= 1
        user.checks_used_total += 1
        db.commit()

        return {
            "allowed": True,
            "checks_remaining": user.checks_remaining,
            "plan": user.plan,
            "upgrade_required": False,
            "message": f"{user.checks_remaining} checks remaining this month.",
        }
    finally:
        db.close()


def get_user_status(user_id: str) -> dict:
    """Get user's current check status."""
    db = SessionLocal()
    try:
        user = db.query(UserRecord).filter(UserRecord.id == user_id).first()
        if not user:
            return get_or_create_user(user_id)
        _reset_if_due(user, db)
        plan_info = PLANS.get(user.plan, PLANS["free"])
        return {
            "user_id": user.id,
            "plan": user.plan,
            "plan_name": plan_info["name"],
            "checks_remaining": user.checks_remaining,
            "checks_per_month": plan_info["checks_per_month"],
            "checks_used_total": user.checks_used_total,
            "features": plan_info["features"],
            "price": plan_info["price"],
        }
    finally:
        db.close()


# ── Result Routing ────────────────────────────────────────────────────────

def filter_result_by_plan(result: dict, plan: str) -> dict:
    """Filter diagnostic result based on user's plan."""
    # During testing — return full results for all users
    return result
    if plan == "pro":
        return result

    basic = {}
    for r in result.get("results", []):
        filtered = {
            "code": r.get("code"),
            "whats_wrong": {
                "summary": r.get("whats_wrong", {}).get("summary", ""),
                "explanation": r.get("whats_wrong", {}).get("explanation", ""),
            },
            "urgency": r.get("urgency"),
            "difficulty": {
                "level": r.get("difficulty", {}).get("level", ""),
                "label": "Upgrade for full details"
            },
            "cost": {"note": "Upgrade to LYLO PRO to see price ranges and scam detection"},
            "shop_script": "Upgrade to LYLO PRO for your personalized ShopScript",
            "red_flags": ["Upgrade to LYLO PRO to see red flags and scam alerts"],
            "locked_features": [
                "price_range", "scam_detection", "shop_script",
                "red_flags", "confidence"
            ],
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


# ── Rate Limiting ─────────────────────────────────────────────────────────

def check_rate_limit(ip: str) -> bool:
    """Returns True if request is allowed, False if rate-limited."""
    db = SessionLocal()
    try:
        now = time.time()
        record = db.query(RateLimit).filter(RateLimit.ip == ip).first()
        if record:
            if now - record.last_request < RATE_LIMIT_SECONDS:
                return False
            record.last_request = now
        else:
            record = RateLimit(ip=ip, last_request=now)
            db.add(record)
        db.commit()
        return True
    finally:
        db.close()


# ── Analytics ─────────────────────────────────────────────────────────────

import json as _json


def log_event(event_type: str, user_id: str = "", details: dict = None):
    """Log an analytics event."""
    db = SessionLocal()
    try:
        event = AnalyticsEvent(
            event=event_type,
            user_id=user_id,
            timestamp=time.time(),
            details=_json.dumps(details or {}),
        )
        db.add(event)
        db.commit()
    finally:
        db.close()


def get_analytics_summary() -> dict:
    """Get analytics summary."""
    db = SessionLocal()
    try:
        total = db.query(AnalyticsEvent).count()
        checks = db.query(AnalyticsEvent).filter(
            AnalyticsEvent.event == "check_used"
        ).count()
        upgrades_clicked = db.query(AnalyticsEvent).filter(
            AnalyticsEvent.event == "upgrade_clicked"
        ).count()
        upgrades_completed = db.query(AnalyticsEvent).filter(
            AnalyticsEvent.event == "upgrade_completed"
        ).count()
        return {
            "total_events": total,
            "checks_used": checks,
            "upgrade_clicks": upgrades_clicked,
            "upgrades_completed": upgrades_completed,
            "conversion_rate": round(
                upgrades_completed / max(upgrades_clicked, 1) * 100, 1
            ),
        }
    finally:
        db.close()
