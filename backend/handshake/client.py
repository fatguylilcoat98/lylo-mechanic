"""
The Good Neighbor Guard — LYLO
Handshake API Client

Calls the-handshake.onrender.com to classify questions before
high-stakes actions. The Handshake is the commit boundary —
it sits between "decision made" and "action taken."

Modes returned:
    LOW_FRICTION   — Safe to proceed, no friction
    SOFT_WARNING   — Proceed with acknowledgment
    FULL_CHECK     — User must articulate their plan before proceeding
    HARD_STOP      — Blocked. Cooling period required.
"""

import requests

HANDSHAKE_URL = "https://the-handshake.onrender.com"
TIMEOUT_SECONDS = 10


def classify(question: str, session_id: str = "") -> dict:
    """
    Send a question to The Handshake for classification.

    Returns the full Handshake response, or a safe fallback
    (LOW_FRICTION) if the service is unreachable.
    """
    try:
        resp = requests.post(
            f"{HANDSHAKE_URL}/classify",
            json={
                "question": question,
                "session_id": session_id,
            },
            timeout=TIMEOUT_SECONDS,
        )
        if resp.ok:
            return resp.json()
    except Exception as e:
        print(f"[HANDSHAKE] Service unreachable: {e}")

    # Fail open — if Handshake is down, don't block the user
    return {
        "mode": "LOW_FRICTION",
        "allowed_to_proceed": True,
        "message": None,
        "risk_score": 0,
        "requires_acknowledgment": False,
        "cooling_period_minutes": 0,
        "fallback": True,
    }


def is_high_stakes(handshake_result: dict) -> bool:
    """Returns True if the Handshake classified this as needing friction."""
    mode = handshake_result.get("mode", "LOW_FRICTION")
    return mode in ("SOFT_WARNING", "FULL_CHECK", "HARD_STOP")


def is_blocked(handshake_result: dict) -> bool:
    """Returns True if the Handshake hard-stopped this action."""
    return handshake_result.get("mode") == "HARD_STOP"


def get_friction_response(handshake_result: dict) -> dict:
    """
    Build a user-facing friction response from the Handshake result.
    Used by the API to inject friction into the response payload.
    """
    mode = handshake_result.get("mode", "LOW_FRICTION")

    if mode == "LOW_FRICTION":
        return {
            "handshake_active": False,
            "mode": "LOW_FRICTION",
            "message": None,
            "requires_acknowledgment": False,
            "blocked": False,
        }

    return {
        "handshake_active": True,
        "mode": mode,
        "message": handshake_result.get("message"),
        "risk_score": handshake_result.get("risk_score", 0),
        "risk_factors": handshake_result.get("risk_factors", []),
        "requires_acknowledgment": handshake_result.get("requires_acknowledgment", False),
        "cooling_period_minutes": handshake_result.get("cooling_period_minutes", 0),
        "next_step_type": handshake_result.get("next_step_type"),
        "blocked": mode == "HARD_STOP",
    }
