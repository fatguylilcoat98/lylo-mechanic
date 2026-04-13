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
import logging
import traceback
from flask import Blueprint, request, jsonify
from models.user import (
    can_run_check, filter_result_by_plan, check_rate_limit, log_event,
    get_user_status,
)
from api.routes.quick_check import (
    _load_data, _is_dtc_code, _extract_codes, _match_symptoms,
    _build_result_for_code,
)

logger = logging.getLogger(__name__)

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
    try:
        logger.info("=== ANALYZE REQUEST STARTED ===")

        # ── Parse request body ────────────────────────────────────────────
        data = request.get_json(force=True) or {}
        logger.info(f"Request data: {data}")

        source = data.get("source", "manual")
        user_id = data.get("user_id", request.remote_addr)
        logger.info(f"source={source} user_id={user_id} remote_addr={request.remote_addr}")

        # ── Rate limit ────────────────────────────────────────────────────
        logger.info("Step: rate limit check")
        if not check_rate_limit(request.remote_addr):
            logger.warning(f"Rate limited: {request.remote_addr}")
            return jsonify({
                "error": "Too many requests. Please wait 20 seconds.",
                "rate_limited": True,
            }), 429

        # ── Check gate (THE money function) ───────────────────────────────
        logger.info("Step: can_run_check gate")
        gate = can_run_check(user_id)
        logger.info(f"Gate result: {gate}")
        if not gate["allowed"]:
            logger.info(f"Check blocked for user_id={user_id}")
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
        logger.info("Step: _load_data()")
        _load_data()
        logger.info("Step: _load_data() complete")

        codes = []
        input_type = source
        user_input = ""
        note = ""

        if source == "obd":
            logger.info("Step: parsing OBD input")
            raw_codes = data.get("codes", [])
            if isinstance(raw_codes, list):
                codes = [c.upper().strip() for c in raw_codes if isinstance(c, str)]
            raw_dtcs = data.get("raw_dtcs", [])
            if raw_dtcs and not codes:
                codes = [d.get("code", "").upper() for d in raw_dtcs if isinstance(d, dict) and d.get("code")]
            user_input = " ".join(codes) if codes else data.get("input", "")
            input_type = "obd_scan"
            logger.info(f"OBD parsed: codes={codes} user_input={user_input!r}")

        else:
            logger.info("Step: parsing manual input")
            user_input = data.get("input", "").strip()
            explicit_codes = data.get("codes", [])
            if explicit_codes:
                codes = [c.upper().strip() for c in explicit_codes if isinstance(c, str)]
            logger.info(f"Manual parsed: codes={codes} user_input={user_input!r}")

        if not codes and not user_input:
            logger.warning("Validation failed: no codes or input")
            return jsonify({"error": "No codes or description provided."}), 400

        # ── Resolve codes ─────────────────────────────────────────────────
        logger.info("Step: resolving codes")
        if codes:
            input_type = "obd_scan" if source == "obd" else "dtc_codes"
        elif _is_dtc_code(user_input):
            codes = [user_input.upper()]
            input_type = "dtc_code"
        else:
            extracted = _extract_codes(user_input)
            if extracted:
                codes = extracted[:3]
                input_type = "codes_in_text"
            else:
                codes = _match_symptoms(user_input)
                input_type = "symptoms"
                note = "Based on your description, here are the most likely issues:"
        logger.info(f"Resolved: input_type={input_type} codes={codes}")

        # ── Build results ─────────────────────────────────────────────────
        logger.info(f"Step: building results for {len(codes[:3])} code(s)")
        results = []
        for c in codes[:3]:
            logger.info(f"  _build_result_for_code({c!r})")
            results.append(_build_result_for_code(c))
        logger.info(f"Built {len(results)} result(s)")

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
        logger.info(f"Step: filter_result_by_plan plan={gate['plan']}")
        filtered = filter_result_by_plan(raw, gate["plan"])
        filtered["checks_remaining"] = gate["checks_remaining"]

        logger.info(f"Analysis result keys: {list(filtered.keys())}")
        logger.info("=== ANALYZE REQUEST COMPLETED ===")
        return jsonify(filtered)

    except Exception as e:
        logger.error(f"ANALYZE FAILED: {str(e)}")
        logger.error(f"Exception type: {type(e).__name__}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        return jsonify({
            "error": str(e),
            "exception_type": type(e).__name__,
        }), 500


@analyze_bp.route("/status", methods=["GET"])
def analyze_status():
    """Quick check: how many checks does this user have left?"""
    user_id = request.args.get("user_id", request.remote_addr)
    return jsonify(get_user_status(user_id))
