"""
LYLO Mechanic — Unified Analysis Endpoint
Christopher Hughes · The Good Neighbor Guard
Truth · Safety · We Got Your Back

ONE endpoint. TWO entry points. ZERO bypasses.

  /api/v1/analyze — the single source of truth for all diagnostics.

  OBD scan → sends codes + vehicle → same endpoint
  Manual input → sends text/codes → same endpoint
  Both go through check gating, plan filtering, rate limiting.

  OBD is NOT the product. OBD is an input method.
  The product is: "Don't get screwed on car repairs."
"""

import re
from flask import Blueprint, request, jsonify
from models.user import (
    can_run_check, filter_result_by_plan, check_rate_limit, log_event,
    get_user_status,
)
from api.routes.quick_check import (
    _load_data, _is_dtc_code, _extract_codes, _match_symptoms,
    _build_result_for_code,
)

analyze_bp = Blueprint("analyze", __name__)


@analyze_bp.route("", methods=["POST"])
def analyze():
    """
    Unified analysis endpoint — single brain, multiple inputs.

    Accepts:
      {
        "source": "obd" | "manual",
        "user_id": "device-fingerprint-or-ip",

        // For OBD source:
        "codes": ["P0302", "P0420"],
        "vehicle": "2015 Honda Civic",       // optional
        "sensor_data": { ... },              // optional, for future use

        // For manual source:
        "input": "car shaking when idling",  // text or code

        // Works for both:
        "codes": ["P0420"],                  // explicit codes override text parsing
      }

    Returns:
      200 — diagnostic result (filtered by plan)
      403 — check limit reached (upgrade required)
      429 — rate limited
    """
    data = request.get_json(force=True) or {}
    source = data.get("source", "manual")
    user_id = data.get("user_id", request.remote_addr)

    # ── Rate limit ────────────────────────────────────────────────────
    if not check_rate_limit(request.remote_addr):
        return jsonify({
            "error": "Too many requests. Please wait 20 seconds.",
            "rate_limited": True,
        }), 429

    # ── Check gate (THE money function) ───────────────────────────────
    gate = can_run_check(user_id)
    if not gate["allowed"]:
        log_event("check_blocked", user_id, {"source": source})
        return jsonify({
            "status": "locked",
            "message": gate["message"],
            "upgrade_required": gate.get("upgrade_required", False),
            "addon_available": gate.get("addon_available", False),
            "checks_remaining": 0,
            "upgrade_url": "/api/v1/billing/upgrade",
        }), 403

    log_event("check_used", user_id, {"source": source})

    # ── Extract codes from input ──────────────────────────────────────
    _load_data()

    codes = []
    input_type = source
    user_input = ""
    note = ""

    if source == "obd":
        # OBD source: codes come directly from the scanner
        raw_codes = data.get("codes", [])
        if isinstance(raw_codes, list):
            codes = [c.upper().strip() for c in raw_codes if isinstance(c, str)]
        # Also accept raw_dtcs format from OBDService.fullScan()
        raw_dtcs = data.get("raw_dtcs", [])
        if raw_dtcs and not codes:
            codes = [d.get("code", "").upper() for d in raw_dtcs if isinstance(d, dict) and d.get("code")]
        user_input = " ".join(codes) if codes else data.get("input", "")
        input_type = "obd_scan"

    else:
        # Manual source: text input or explicit codes
        user_input = data.get("input", "").strip()
        explicit_codes = data.get("codes", [])
        if explicit_codes:
            codes = [c.upper().strip() for c in explicit_codes if isinstance(c, str)]

    if not codes and not user_input:
        return jsonify({"error": "No codes or description provided."}), 400

    # ── Resolve codes ─────────────────────────────────────────────────

    if codes:
        # Direct codes (from OBD or explicit)
        input_type = "obd_scan" if source == "obd" else "dtc_codes"
    elif _is_dtc_code(user_input):
        codes = [user_input.upper()]
        input_type = "dtc_code"
    else:
        # Try extracting codes from text
        extracted = _extract_codes(user_input)
        if extracted:
            codes = extracted[:3]
            input_type = "codes_in_text"
        else:
            # Symptom matching
            codes = _match_symptoms(user_input)
            input_type = "symptoms"
            note = "Based on your description, here are the most likely issues:"

    # ── Build results ─────────────────────────────────────────────────

    results = [_build_result_for_code(c) for c in codes[:3]]

    raw = {
        "input": user_input or " ".join(codes),
        "input_type": input_type,
        "source": source,
        "results": results,
    }
    if note:
        raw["note"] = note
    if data.get("vehicle"):
        raw["vehicle"] = data["vehicle"]

    # ── Filter by plan ────────────────────────────────────────────────

    filtered = filter_result_by_plan(raw, gate["plan"])
    filtered["checks_remaining"] = gate["checks_remaining"]

    return jsonify(filtered)


@analyze_bp.route("/status", methods=["GET"])
def analyze_status():
    """Quick check: how many checks does this user have left?"""
    user_id = request.args.get("user_id", request.remote_addr)
    return jsonify(get_user_status(user_id))
