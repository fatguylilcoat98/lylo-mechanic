"""
The Good Neighbor Guard — LYLO Mechanic
Christopher Hughes · Sacramento, CA
AI Collaborators: Claude · GPT · Gemini · Groq
Truth · Safety · We Got Your Back

Live OBD endpoint — accepts real data from mobile app
"""

from flask import Blueprint, jsonify, request
from api.orchestrator import run_diagnosis
from models.schemas import (
    OBDSessionInput, VehicleProfile, RawDTC, RawPIDValue,
    ReadinessMonitor, SymptomIntake
)

live_bp = Blueprint("live", __name__)


@live_bp.route("/live", methods=["POST"])
def diagnose_live():
    """
    Accept real OBDLink data from the mobile app.
    Runs through the full LYLO diagnostic pipeline.
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    try:
        # Build raw DTCs from mobile payload
        raw_dtcs = []
        for dtc in data.get("raw_dtcs", []):
            raw_dtcs.append(RawDTC(
                code=dtc.get("code", "").upper(),
                status=dtc.get("status", "active"),
                description=dtc.get("description"),
            ))

        # Build raw PIDs from mobile payload
        raw_pids = []
        for pid in data.get("raw_pids", []):
            val = pid.get("raw_value")
            raw_pids.append(RawPIDValue(
                name=pid.get("name", ""),
                pid_code=pid.get("pid_code", ""),
                raw_value=float(val) if val is not None else None,
                unit=pid.get("unit", ""),
            ))

        # Build vehicle profile
        vp_data = data.get("vehicle_profile", {})
        vehicle_profile = VehicleProfile(
            year=vp_data.get("year"),
            make=vp_data.get("make"),
            model=vp_data.get("model"),
            engine=vp_data.get("engine"),
            is_hybrid=vp_data.get("is_hybrid", False),
            is_ev=vp_data.get("is_ev", False),
            odometer=vp_data.get("odometer"),
        )

        # Build session
        session = OBDSessionInput(
            adapter_id=data.get("adapter_id", "OBDLink_MX+"),
            protocol=data.get("protocol", "ISO 9141-2"),
            connection_quality=data.get("connection_quality", "stable"),
            read_complete=data.get("read_complete", True),
            vehicle_profile=vehicle_profile,
            raw_dtcs=raw_dtcs,
            raw_pids=raw_pids,
            readiness_monitors=[],
            codes_cleared_before_scan=data.get("codes_cleared_before_scan", False),
        )

        # Build symptoms if provided
        symptoms = None
        if data.get("symptoms"):
            sym = data["symptoms"]
            symptoms = SymptomIntake(
                primary_category=sym.get("primary_category", "warning_light_only"),
                severity=sym.get("severity", "noticeable"),
                frequency=sym.get("frequency", "occasional"),
            )

        # Run the full pipeline
        result = run_diagnosis(session, symptoms)
        return jsonify(result.to_dict())

    except Exception as e:
        return jsonify({"error": str(e)}), 500
