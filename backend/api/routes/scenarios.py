"""
The Good Neighbor Guard — LYLO Mechanic
Scenario listing route
"""
from flask import Blueprint, jsonify

scenarios_bp = Blueprint("scenarios", __name__)


@scenarios_bp.route("/list", methods=["GET"])
def list_scenarios():
    from demo_scenarios.scenarios import list_scenarios
    return jsonify(list_scenarios())
