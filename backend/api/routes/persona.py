"""
The Good Neighbor Guard — LYLO
Persona API routes

/api/v1/persona/list          — list all personas
/api/v1/persona/ask           — ask a question to a specific persona
/api/v1/persona/classify      — auto-detect which persona should handle a question
"""

from flask import Blueprint, jsonify, request
from personas.router import (
    PERSONAS, classify_persona, check_lane,
    get_persona_info, list_personas,
)
from handshake.client import classify as handshake_classify, get_friction_response, is_blocked
import os

persona_bp = Blueprint("persona", __name__)


@persona_bp.route("/list", methods=["GET"])
def persona_list():
    """Return all available personas."""
    return jsonify({"personas": list_personas()})


@persona_bp.route("/classify", methods=["POST"])
def persona_classify():
    """Auto-detect which persona should handle a question."""
    data = request.get_json() or {}
    question = (data.get("question") or "").strip()
    if not question:
        return jsonify({"error": "question is required"}), 400

    suggested = classify_persona(question)
    return jsonify({
        "suggested_persona": suggested,
        "persona": get_persona_info(suggested),
    })


@persona_bp.route("/ask", methods=["POST"])
def persona_ask():
    """
    Ask a question to a specific persona.

    Required: question, persona
    Optional: session_id

    Flow:
        1. Lane check — is this question in the persona's domain?
        2. If not → redirect (do NOT answer)
        3. If yes → Handshake check (is this high-stakes?)
        4. If Handshake blocks → return friction response
        5. If clear → route to persona engine
    """
    data = request.get_json() or {}
    question = (data.get("question") or "").strip()
    persona_id = (data.get("persona") or "").strip().lower()
    session_id = data.get("session_id", "")

    if not question:
        return jsonify({"error": "question is required"}), 400
    if not persona_id or persona_id not in PERSONAS:
        return jsonify({"error": f"Valid persona required. Options: {', '.join(PERSONAS.keys())}"}), 400

    # ── STEP 1: LANE CHECK ────────────────────────────────────────────────────
    lane = check_lane(persona_id, question)

    if not lane["in_lane"]:
        return jsonify({
            "ok": True,
            "redirected": True,
            "persona": persona_id,
            "suggested_persona": lane["suggested_persona"],
            "message": lane["redirect_message"],
            "answer": None,
        })

    # ── STEP 2: HANDSHAKE CHECK ───────────────────────────────────────────────
    hs_result = handshake_classify(question, session_id)
    friction = get_friction_response(hs_result)

    if is_blocked(hs_result):
        return jsonify({
            "ok": True,
            "redirected": False,
            "persona": persona_id,
            "blocked": True,
            "handshake": friction,
            "answer": None,
            "message": friction.get("message", "This action has been paused for your safety."),
        })

    # ── STEP 3: ROUTE TO PERSONA ENGINE ───────────────────────────────────────

    if persona_id == "mechanic":
        # Mechanic uses the existing diagnostic pipeline — redirect to /api/v1/diagnose
        return jsonify({
            "ok": True,
            "redirected": False,
            "persona": "mechanic",
            "route_to": "/api/v1/diagnose",
            "message": "Use the Mechanic diagnostic interface for vehicle questions.",
            "handshake": friction,
            "answer": None,
        })

    # Non-mechanic personas: Claude-powered response with lane-locked system prompt
    answer = _ask_claude(persona_id, question)

    return jsonify({
        "ok": True,
        "redirected": False,
        "persona": persona_id,
        "answer": answer,
        "handshake": friction,
        "blocked": False,
    })


def _ask_claude(persona_id: str, question: str) -> str:
    """
    Call Claude with the persona's system prompt.
    Falls back to a safe message if API key is missing or call fails.
    """
    persona = PERSONAS[persona_id]
    api_key = os.environ.get("ANTHROPIC_API_KEY")

    if not api_key:
        return (
            f"[LYLO {persona['name']}] I'm here to help, but my AI engine isn't connected yet. "
            "The team is working on it. In the meantime, know that someone cares. "
            "Truth. Safety. We Got Your Back."
        )

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=800,
            system=persona["system_prompt"],
            messages=[{"role": "user", "content": question}],
        )
        return msg.content[0].text
    except Exception as e:
        return (
            f"[LYLO {persona['name']}] I hit a snag trying to respond — "
            f"but I'm still here. Try again in a moment. ({str(e)[:80]})"
        )
