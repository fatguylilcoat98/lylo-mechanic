"""
The Good Neighbor Guard — LYLO Mechanic
Tutorial route
"""
from flask import Blueprint, jsonify

tutorial_bp = Blueprint("tutorial", __name__)

@tutorial_bp.route("/<cause_id>", methods=["GET"])
def get_tutorial(cause_id):
    AVAILABLE = ["spark_plug_cyl1","ignition_coil_cyl1","faulty_downstream_o2","wrong_oil_viscosity","vacuum_leak"]
    if cause_id not in AVAILABLE:
        return jsonify({"available": False, "reason": f"Tutorial for '{cause_id}' not yet in content library."})
    return jsonify({"available": True, "cause_id": cause_id, "note": "Full tutorial content in Phase 5."})
