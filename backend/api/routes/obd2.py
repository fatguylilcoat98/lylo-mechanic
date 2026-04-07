"""
The Good Neighbor Guard — LYLO Mechanic
Christopher Hughes · Sacramento, CA
AI Collaborators: Claude · GPT · Gemini · Groq
Truth · Safety · We Got Your Back
"""

from flask import Blueprint, jsonify, request
from api.orchestrator import run_diagnosis
from models.schemas import OBDSessionInput

obd2_bp = Blueprint("obd2", __name__)


@obd2_bp.route("/obd2", methods=["POST"])
def diagnose_obd2():
    """
    Main endpoint for LYLO Mechanic mobile app.
    Accepts real OBD2 fault codes and live data from the vehicle.
    
    Request format:
    {
        "dtc_codes": ["P0101", "C0101", "P0007"],
        "live_data": {
            "rpm": 1200,
            "speed": 0,
            "coolant_temp": 197,
            "battery_voltage": 14.1,
            "fuel_trim_bank1": 4.7,
            "fuel_trim_bank2": -2.3,
            "throttle_position": 0.15,
            "maf_flow": 6.5,
            "intake_air_temp": 68
        },
        "vehicle_info": {
            "vin": "2G1FB1E39D1234567",
            "year": 2009,
            "make": "Honda",
            "model": "Accord"
        }
    }
    """
    
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
        
        dtc_codes = data.get("dtc_codes", [])
        live_data = data.get("live_data", {})
        vehicle_info = data.get("vehicle_info", {})
        
        if not dtc_codes:
            return jsonify({"error": "No DTC codes provided"}), 400
        
        # Build OBDSessionInput for diagnosis engine
        session_input = OBDSessionInput(
            dtc_codes=dtc_codes,
            live_data=live_data,
            vehicle_info=vehicle_info
        )
        
        # Run full diagnosis pipeline
        result = run_diagnosis(
            session_input=session_input,
            symptoms=None,
            extra_flags=["obd_live_data"]  # Flag that this is real hardware data
        )
        
        # Format response for mobile app
        response = {
            "status": "success",
            "dtc_codes": dtc_codes,
            "vehicle": vehicle_info,
            "diagnosis": result.to_dict(),
            "timestamp": __import__('datetime').datetime.now().isoformat()
        }
        
        return jsonify(response), 200
        
    except Exception as e:
        return jsonify({
            "status": "error",
            "error": str(e),
            "detail": "Diagnosis engine failed"
        }), 500
