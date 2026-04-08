"""
Veracore — The Good Neighbor Guard
Built by Christopher Hughes · Sacramento, CA
Created with the help of AI collaborators (Claude · GPT · Gemini · Groq)
Truth · Safety · We Got Your Back

Truth System API Routes

POST /truth          — Truth/deception analysis of a scan
POST /health         — Preventative failure signal analysis
POST /blackbox/snap  — Record a data snapshot (returns event if triggered)
GET  /blackbox/events — List recorded events
POST /blackbox/clear  — Clear the event buffer
POST /audit          — Audit a mechanic's quote against evidence
POST /scan           — Combined: runs truth + health in one call
"""

from flask import Blueprint, request, jsonify
from truth_detector import analyze_truth, truth_report_to_dict
from failure_predictor import analyze_health, health_report_to_dict
from event_blackbox import BlackBox
from quote_auditor import audit_quote, audit_result_to_dict


truth_bp = Blueprint("truth", __name__)


# Singleton BlackBox for in-process event buffering.
# In production this would be per-user/per-session in a persistent store.
_blackbox = BlackBox()


# ── TRUTH DETECTOR ───────────────────────────────────────────────────────

@truth_bp.route("/truth", methods=["POST"])
def truth_endpoint():
    """Analyze OBD data for deception signals.

    Body: OBD data dict (dtcs, pending_dtcs, monitors, fuel_trim_long,
          o2_voltage, time_since_clear, freeze_frame, etc.)
    """
    data = request.get_json(force=True) or {}
    report = analyze_truth(data)
    return jsonify(truth_report_to_dict(report))


# ── FAILURE PREDICTOR ────────────────────────────────────────────────────

@truth_bp.route("/health", methods=["POST"])
def health_endpoint():
    """Analyze OBD sensor data for early failure warnings.

    Body: OBD data dict (battery_voltage, coolant_temp, fuel_trim_long, etc.)
    """
    data = request.get_json(force=True) or {}
    report = analyze_health(data)
    return jsonify(health_report_to_dict(report))


# ── EVENT BLACK BOX ──────────────────────────────────────────────────────

@truth_bp.route("/blackbox/snap", methods=["POST"])
def blackbox_snap():
    """Record a single data snapshot. Returns event if triggered.

    Body: {rpm, speed, throttle_position, engine_load, coolant_temp, brake_active}
    """
    data = request.get_json(force=True) or {}
    event = _blackbox.record_snapshot(data)
    if event is None:
        return jsonify({"event": None, "buffer_size": len(_blackbox.buffer)})
    return jsonify({
        "event": {
            "type": event.event_type.value,
            "triggered_at": event.triggered_at,
            "summary": event.human_summary,
            "severity": event.severity,
            "peak_values": event.peak_values,
        },
        "buffer_size": len(_blackbox.buffer),
        "total_events": len(_blackbox.events),
    })


@truth_bp.route("/blackbox/events", methods=["GET"])
def blackbox_events():
    """Return all recorded events."""
    return jsonify({
        "count": len(_blackbox.events),
        "events": _blackbox.get_events(),
    })


@truth_bp.route("/blackbox/clear", methods=["POST"])
def blackbox_clear():
    """Clear the event buffer and history."""
    _blackbox.clear()
    return jsonify({"cleared": True})


# ── QUOTE AUDITOR ────────────────────────────────────────────────────────

@truth_bp.route("/audit", methods=["POST"])
def audit_endpoint():
    """Audit a mechanic's quote against OBD data.

    Body: {
      "quote": "You need a new catalytic converter, $1,800",
      "obd_data": { dtcs: [...], fuel_trim_long: ..., etc. }
    }
    """
    payload = request.get_json(force=True) or {}
    quote_text = payload.get("quote", "")
    obd_data = payload.get("obd_data", {})

    if not quote_text:
        return jsonify({"error": "quote field is required"}), 400

    result = audit_quote(quote_text, obd_data)
    return jsonify(audit_result_to_dict(result))


# ── COMBINED SCAN ────────────────────────────────────────────────────────

@truth_bp.route("/scan", methods=["POST"])
def combined_scan():
    """The main endpoint. Runs truth + health analysis in one call.

    Body: OBD data dict (see /truth and /health for fields)

    Optional:
      "quote": if present, also runs quote auditor
    """
    data = request.get_json(force=True) or {}
    quote = data.pop("quote", None)

    truth = analyze_truth(data)
    health = analyze_health(data)

    response = {
        # Truth layer
        "truth_status": truth.status.value,
        "truth_headline": truth.headline,
        "truth_detail": truth.detail,
        "truth_confidence": truth.confidence,
        "truth_signals": [
            {
                "signal": s.signal.value,
                "severity": s.severity,
                "explanation": s.human_explanation,
            }
            for s in truth.signals
        ],
        "truth_recommendations": truth.recommendations,

        # Health layer
        "health_status": health.overall_status.value,
        "health_headline": health.headline,
        "health_signals": [
            {
                "system": s.system,
                "status": s.status.value,
                "explanation": s.human_explanation,
                "urgency": s.urgency,
                "timeline": s.estimated_timeline,
            }
            for s in health.signals
        ],
        "health_recommendations": health.recommendations,

        # Event log (from the shared blackbox)
        "event_log": _blackbox.get_events(),
    }

    # Optional quote audit
    if quote:
        audit = audit_quote(quote, data)
        response["quote_audit"] = audit_result_to_dict(audit)

    return jsonify(response)
