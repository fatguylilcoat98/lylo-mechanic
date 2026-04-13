"""
The Good Neighbor Guard — LYLO Mechanic
Christopher Hughes · Sacramento, CA
AI Collaborators: Claude · GPT · Gemini · Groq
Truth · Safety · We Got Your Back
"""

from flask import Blueprint, jsonify, request
from api.orchestrator import run_diagnosis
from auth import require_auth

diagnose_bp = Blueprint("diagnose", __name__)


@diagnose_bp.route("/scenario/<scenario_id>", methods=["POST"])
@require_auth
def diagnose_scenario(scenario_id):
    """Run diagnosis on a named demo scenario."""
    from demo_scenarios.scenarios import get_scenario

    scenario = get_scenario(scenario_id)
    if not scenario:
        return jsonify({"error": f"Unknown scenario: {scenario_id}"}), 404

    session_input = scenario["session"]
    symptoms = scenario.get("symptoms")
    extra_flags = scenario.get("extra_flags", [])

    result = run_diagnosis(session_input, symptoms, extra_flags)
    return jsonify(result.to_dict())


@diagnose_bp.route("/run", methods=["POST"])
@require_auth
def diagnose_raw():
    """
    Run diagnosis on raw submitted data.
    STUB: Currently accepts JSON matching OBDSessionInput shape.
    Full OBDLink hardware integration replaces this endpoint.
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    # For now, route to scenario if scenario_id is provided
    scenario_id = data.get("scenario_id")
    if scenario_id:
        from demo_scenarios.scenarios import get_scenario
        scenario = get_scenario(scenario_id)
        if scenario:
            result = run_diagnosis(scenario["session"], scenario.get("symptoms"), scenario.get("extra_flags", []))
            return jsonify(result.to_dict())

    return jsonify({"error": "Direct OBDLink ingestion not yet wired — use /scenario/<id>"}), 501
