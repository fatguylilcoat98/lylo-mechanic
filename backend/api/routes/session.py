"""
The Good Neighbor Guard — LYLO Mechanic
Session routes
"""
from flask import Blueprint, jsonify

session_bp = Blueprint("session", __name__)


@session_bp.route("/ping", methods=["GET"])
def ping():
    return jsonify({"status": "ok", "adapter": "SIMULATED — OBDLink hardware integration pending"})
