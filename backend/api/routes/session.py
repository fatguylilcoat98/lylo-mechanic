"""
The Good Neighbor Guard — LYLO Mechanic
Session and tutorial routes
"""
from flask import Blueprint, jsonify

session_bp = Blueprint("session", __name__)
tutorial_bp = Blueprint("tutorial", __name__)


@session_bp.route("/ping", methods=["GET"])
def ping():
    return jsonify({"status": "ok", "adapter": "SIMULATED — OBDLink hardware integration pending"})


@tutorial_bp.route("/<cause_id>", methods=["GET"])
def get_tutorial(cause_id):
    """
    STUB: Returns a placeholder tutorial structure.
    Full tutorial content library is Phase 5.
    """
    AVAILABLE = ["spark_plug_cyl1", "ignition_coil_cyl1", "faulty_downstream_o2",
                 "wrong_oil_viscosity", "vacuum_leak"]
    if cause_id not in AVAILABLE:
        return jsonify({
            "available": False,
            "reason": f"Tutorial for '{cause_id}' not yet in content library. Check back or consult a professional."
        })

    return jsonify({
        "available": True,
        "cause_id": cause_id,
        "note": "Full tutorial content returns in Phase 5 build. Gate logic is live.",
    })
