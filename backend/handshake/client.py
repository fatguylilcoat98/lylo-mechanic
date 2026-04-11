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
CLASPION_URL = "https://the-handshake.onrender.com/claspion/decision"
TIMEOUT_SECONDS = 10


def classify_with_claspion(question: str, session_id: str = "") -> dict:
    """
    Use local CLASPION for enhanced security classification.
    Returns enhanced verification result with audit trail.
    """
    try:
        # Import local CLASPION
        from claspion import evaluate

        # Run local CLASPION evaluation
        decision = evaluate(question, session_id=session_id)

        # Convert CLASPION decision to Handshake-compatible format
        is_blocked = decision.decision == 'BLOCKED'

        # Map CLASPION decision to friction levels
        if is_blocked:
            friction_level = "HARD_STOP"
        else:
            # Use risk score to determine friction level
            risk_score = 0.0
            if hasattr(decision, 'layer_trail'):
                for layer in decision.layer_trail:
                    if layer.get('layer') == 'SEMANTIC_CLASSIFIER':
                        risk_score = layer.get('combined_risk_score', 0.0)
                        break

            if risk_score > 0.7:
                friction_level = "FULL_CHECK"
            elif risk_score > 0.3:
                friction_level = "SOFT_WARNING"
            else:
                friction_level = "LOW_FRICTION"

        return {
            "mode": friction_level,
            "confidence": getattr(decision, 'confidence', 0.9),
            "reason": decision.reason or '',
            "claspion_enhanced": True,
            "claspion_local": True,
            "layers_checked": len(getattr(decision, 'layer_trail', [])),
            "audit_trail": getattr(decision, 'layer_trail', []),
            "decision_object": decision
        }

    except Exception as e:
        print(f"Local CLASPION classification failed: {e}")
        # Fallback to original handshake
        return classify(question, session_id)


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
