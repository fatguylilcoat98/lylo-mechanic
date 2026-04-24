"""
The Good Neighbor Guard — LYLO Mechanic
Christopher Hughes · Sacramento, CA
AI Collaborators: Claude · GPT · Gemini · Groq
Truth · Safety · We Got Your Back

Quick Check MVP endpoint — the consumer-facing diagnostic engine.
Takes a DTC code or plain-English symptom description and returns
actionable results: what's wrong, urgency, cost, difficulty, ShopScript, red flags.
"""

import json
import os
import re
from pathlib import Path
from flask import Blueprint, request, jsonify, g

from auth import require_auth

quick_check_bp = Blueprint("quick_check", __name__)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"

def _enhance_with_claspion_verification(results, user_input):
    """Enhance results with local CLASPION verification."""
    try:
        # Import local CLASPION
        from claspion import evaluate

        for result in results:
            # Build verification prompt from result
            code = result.get('code', '')
            summary = result.get('whats_wrong', {}).get('summary', '')
            urgency = result.get('urgency', {}).get('level', '')

            verification_prompt = f"Vehicle diagnostic: {code} - {summary}. Urgency level: {urgency}. Recommend proceeding with repair."

            # Run local CLASPION verification
            decision = evaluate(verification_prompt, session_id=f"lylo-quick-{hash(user_input)}")

            # Extract verification metrics
            risk_score = 0.0
            layers_passed = []

            if hasattr(decision, 'layer_trail') and decision.layer_trail:
                for layer in decision.layer_trail:
                    layers_passed.append({
                        "layer": layer.get('layer', 'unknown'),
                        "status": "passed" if not layer.get('blocked', False) else "blocked",
                        "score": layer.get('score', 0.0)
                    })

                    if layer.get('layer') == 'SEMANTIC_CLASSIFIER':
                        risk_score = layer.get('combined_risk_score', 0.0)

            # Add CLASPION verification to result
            result['claspion_verification'] = {
                "decision": decision.decision,
                "risk_score": risk_score,
                "confidence": getattr(decision, 'confidence', 0.9),
                "reason": decision.reason or '',
                "layers_passed": layers_passed,
                "timestamp": decision.timestamp,
                "local_claspion": True
            }

    except Exception as e:
        print(f"Local CLASPION verification failed: {e}")
        # Add fallback verification for all results
        for result in results:
            result['claspion_verification'] = {
                "decision": "ALLOWED",
                "risk_score": 0.0,
                "confidence": 0.7,
                "reason": "CLASPION verification unavailable",
                "layers_passed": [],
                "timestamp": "",
                "local_claspion": False
            }

    return results
DTC_DB = {}
CAUSE_MAP = {}
REPAIR_COSTS = {}

# Symptom-to-code mapping for common descriptions (no API call needed)
SYMPTOM_MAP = {
    "check engine light": ["P0420", "P0171", "P0300"],
    "rough idle": ["P0300", "P0171", "P0301"],
    "misfire": ["P0300", "P0301", "P0302"],
    "catalytic converter": ["P0420"],
    "battery": ["P0562"],
    "battery light": ["P0562"],
    "car won't start": ["P0562", "P0335"],
    "won't start": ["P0562", "P0335"],
    "no start": ["P0562", "P0335"],
    "overheating": ["P0217"],
    "running hot": ["P0217"],
    "temperature high": ["P0217"],
    "gas cap": ["P0440", "P0455"],
    "fuel smell": ["P0171", "P0172"],
    "exhaust smell": ["P0420", "P0171"],
    "vibration": ["NO_CODE_VIBRATION"],
    "shaking": ["NO_CODE_VIBRATION"],
    "brakes": ["NO_CODE_BRAKE"],
    "brake squeal": ["NO_CODE_BRAKE"],
    "squealing": ["NO_CODE_BRAKE"],
    "grinding": ["NO_CODE_BRAKE"],
    "lean": ["P0171"],
    "rich": ["P0172"],
    "oil light": ["P0011"],
    "stalling": ["P0300", "P0171", "P0335"],
    "hesitation": ["P0171", "P0300"],
    "sluggish": ["P0171", "P0101"],
    "poor gas mileage": ["P0420", "P0171", "P0172"],
    "bad gas mileage": ["P0420", "P0171", "P0172"],
    "ticking noise": ["P0420"],
    "rattling": ["P0011"],
    "humming": ["NO_CODE_VIBRATION"],
}


def _load_data():
    global DTC_DB, CAUSE_MAP, REPAIR_COSTS
    if not DTC_DB:
        with open(DATA_DIR / "dtc_db" / "dtc_codes.json") as f:
            DTC_DB = json.load(f)
    if not CAUSE_MAP:
        with open(DATA_DIR / "hypothesis_rules" / "cause_map.json") as f:
            CAUSE_MAP = json.load(f)
    if not REPAIR_COSTS:
        with open(DATA_DIR / "pricing" / "repair_costs.json") as f:
            REPAIR_COSTS = json.load(f)


def _is_dtc_code(text: str) -> bool:
    """Check if input looks like a DTC code (P0420, C0035, B0001, U0100)."""
    return bool(re.match(r'^[PCBU]\d{4}$', text.strip().upper()))


def _extract_codes(text: str) -> list[str]:
    """Extract any DTC codes embedded in freeform text."""
    return re.findall(r'[PCBU]\d{4}', text.upper())


def _match_symptoms(text: str) -> list[str]:
    """Match freeform symptom text to likely DTC codes."""
    text_lower = text.lower()
    matched_codes = []
    for keyword, codes in SYMPTOM_MAP.items():
        if keyword in text_lower:
            for code in codes:
                if code not in matched_codes:
                    matched_codes.append(code)
    # If nothing matched, default to generic check engine
    if not matched_codes:
        matched_codes = ["P0420", "P0300"]
    return matched_codes[:3]


def _get_urgency(code: str, dtc_info: dict, cause_map_entry: dict) -> dict:
    """Determine urgency level."""
    safety_related = dtc_info.get("safety_related", False)

    # Emergency codes
    if code in ("P0217",):
        return {
            "level": "DO NOT DRIVE",
            "color": "red",
            "message": "Stop driving immediately. This condition can cause permanent engine damage."
        }

    # Safety-critical
    if code in ("P0335", "B0001", "U0100") or (code.startswith("NO_CODE_BRAKE")):
        return {
            "level": "DO NOT DRIVE",
            "color": "red",
            "message": "This affects critical safety systems. Get it inspected before driving."
        }

    if safety_related or code.startswith("P030") or code == "P0007":
        return {
            "level": "INSPECT SOON",
            "color": "orange",
            "message": "Safe for short drives, but get it checked within a few days. Continued driving may cause more damage."
        }

    # Non-safety
    return {
        "level": "SAFE TO DRIVE",
        "color": "green",
        "message": "You can keep driving, but schedule a repair to avoid bigger issues down the line."
    }


def _get_difficulty(cause_id: str) -> dict:
    """Determine fix difficulty from cost data."""
    cost_entry = REPAIR_COSTS.get(cause_id, {})
    diy_time = cost_entry.get("diy_time", "")

    if "NOT DIY" in diy_time.upper():
        return {"level": "Hard", "label": "Shop recommended", "icon": "wrench"}
    if any(x in cause_id for x in ["timing_chain", "head_gasket", "transmission", "wheel_bearing"]):
        return {"level": "Hard", "label": "Shop recommended", "icon": "wrench"}
    if any(x in cause_id for x in ["spark_plug", "ignition_coil", "battery", "oil", "gas_cap"]):
        return {"level": "Easy", "label": "DIY friendly", "icon": "thumbs-up"}

    # Medium by default
    return {"level": "Medium", "label": "Experienced DIY or shop", "icon": "tool"}


def _get_cost_range(cause_id: str) -> dict:
    """Pull cost range from repair costs data."""
    cost_entry = REPAIR_COSTS.get(cause_id)
    if not cost_entry:
        return {
            "diy": "$50 – $200 (estimate)",
            "shop": "$150 – $500 (estimate)",
            "note": "Cost varies by vehicle. Get a quote before approving work."
        }

    diy_low = cost_entry.get("diy_parts_low", 0) + cost_entry.get("diy_tool_cost", 0)
    diy_high = cost_entry.get("diy_parts_high", 0) + cost_entry.get("diy_tool_cost", 0)
    shop_low = cost_entry.get("shop_parts_low", 0) + cost_entry.get("shop_labor_low", 0)
    shop_high = cost_entry.get("shop_parts_high", 0) + cost_entry.get("shop_labor_high", 0)
    dealer_low = cost_entry.get("dealer_total_low", 0)
    dealer_high = cost_entry.get("dealer_total_high", 0)

    return {
        "diy": f"${diy_low} – ${diy_high}" if diy_low else "N/A",
        "shop": f"${shop_low} – ${shop_high}",
        "dealer": f"${dealer_low} – ${dealer_high}" if dealer_low else None,
        "note": cost_entry.get("dealer_note", "Prices are US national averages. Your area may vary ±30%.")
    }


def _build_shop_script(code: str, top_cause: dict, cost_range: dict) -> str:
    """Generate the ShopScript — what to say at the mechanic."""
    cause_name = top_cause.get("name", "the issue")
    cause_desc = top_cause.get("description", "")

    # Extract other possible causes
    all_causes = CAUSE_MAP.get(code, {}).get("causes", [])
    other_causes = [c["name"] for c in all_causes[1:3]] if len(all_causes) > 1 else []

    script = f'"I\'m getting code {code}. '

    if other_causes:
        script += f'I understand it could be {top_cause["name"]}'
        script += f', or possibly {other_causes[0]}'
        if len(other_causes) > 1:
            script += f' or {other_causes[1]}'
        script += '. '
    else:
        script += f'I understand it\'s likely related to {cause_name}. '

    script += 'Can you run a diagnostic to confirm before replacing anything? '
    script += f'I\'m expecting the repair to be in the {cost_range["shop"]} range — does that sound right?"'

    return script


def _build_red_flags(code: str, top_cause: dict) -> list[str]:
    """Generate red flags — things to watch out for at the shop."""
    flags = []

    cost_entry = REPAIR_COSTS.get(top_cause.get("id", ""), {})
    estimate_wrong = cost_entry.get("estimate_wrong_if", [])
    for note in estimate_wrong[:2]:
        flags.append(note)

    # Code-specific red flags
    if code == "P0420":
        flags.insert(0, "If they immediately recommend catalytic converter replacement without testing O2 sensors and checking for exhaust leaks first — that's a red flag. P0420 is the most misdiagnosed code in the industry.")
    elif code.startswith("P030"):
        flags.insert(0, "If they want to replace all ignition coils at once without testing which cylinder is misfiring — ask them to confirm the failing cylinder first.")
    elif code == "P0562":
        flags.insert(0, "If they jump straight to alternator replacement without load-testing the battery first — push back. Battery test takes 5 minutes and is usually free.")
    elif code == "P0217":
        flags.insert(0, "If they say 'head gasket' without running a compression test or block test — get a second opinion.")

    if not flags:
        flags.append("If the quote is significantly above the range shown here, ask for an itemized breakdown of parts and labor.")
        flags.append("Always ask: 'Is there a cheaper fix we should try first before the expensive repair?'")

    return flags


def _build_result_for_code(code: str) -> dict:
    """Build the full MVP result for a single DTC code."""
    _load_data()

    dtc_info = DTC_DB.get(code, {})
    cause_entry = CAUSE_MAP.get(code, {})
    causes = cause_entry.get("causes", [])
    check_first = cause_entry.get("check_first", [])

    if not dtc_info and not causes:
        # Unknown code — give generic helpful response
        return {
            "code": code,
            "whats_wrong": {
                "summary": f"Code {code} was detected. This is a diagnostic trouble code stored by your vehicle's computer.",
                "details": "We don't have this specific code in our database yet, but a mechanic with a professional scan tool can tell you exactly what it means for your vehicle.",
                "check_first": ["Get a professional diagnostic scan — most shops charge $50-100 for this"]
            },
            "urgency": {
                "level": "INSPECT SOON",
                "color": "orange",
                "message": "We recommend getting this checked by a professional to determine severity."
            },
            "cost": {
                "diy": "Unknown",
                "shop": "$100 – $500 (diagnostic + typical repair)",
                "note": "Cost depends on what the code means for your specific vehicle."
            },
            "difficulty": {"level": "Unknown", "label": "Professional diagnosis recommended", "icon": "wrench"},
            "shop_script": f'"I\'m getting code {code}. Can you run a full diagnostic and tell me what\'s going on before we talk about repairs? I\'d like to understand the issue and get a written estimate before approving any work."',
            "red_flags": [
                "If they want to start repairs without explaining what the code means — ask for an explanation first.",
                "Always ask for a written estimate before any work begins.",
                "If the quote feels high, it's okay to say 'Let me get a second opinion.'"
            ]
        }

    top_cause = causes[0] if causes else {}
    cause_id = top_cause.get("id", "")

    # What's likely wrong
    description = dtc_info.get("description", f"Diagnostic code {code}")
    summary = top_cause.get("description", description)
    other_possibilities = [c["name"] for c in causes[1:3]]

    whats_wrong = {
        "summary": f"{description}",
        "likely_cause": top_cause.get("name", "Unknown"),
        "explanation": summary,
        "other_possibilities": other_possibilities,
        "check_first": check_first
    }

    urgency = _get_urgency(code, dtc_info, cause_entry)
    cost = _get_cost_range(cause_id)
    difficulty = _get_difficulty(cause_id)
    shop_script = _build_shop_script(code, top_cause, cost)
    red_flags = _build_red_flags(code, top_cause)

    return {
        "code": code,
        "whats_wrong": whats_wrong,
        "urgency": urgency,
        "cost": cost,
        "difficulty": difficulty,
        "shop_script": shop_script,
        "red_flags": red_flags
    }


# ── Demo scenarios ────────────────────────────────────────────────
DEMOS = {
    "p0420": {
        "id": "p0420",
        "label": "P0420 — Check Engine Light",
        "description": "The most common check engine code. See why shops get this one wrong.",
        "input": "P0420"
    },
    "misfire": {
        "id": "misfire",
        "label": "Engine Misfire",
        "description": "Rough idle, engine shaking, loss of power.",
        "input": "Engine is shaking, rough idle, feels like it's going to stall"
    },
    "battery": {
        "id": "battery",
        "label": "Battery / Electrical Issues",
        "description": "Dim lights, slow crank, electrical gremlins.",
        "input": "P0562"
    }
}


@quick_check_bp.route("/check", methods=["POST"])
@require_auth
def quick_check():
    """
    Main MVP endpoint — gated by plan and check limits.
    Accepts: {"input": "P0420"}
    Returns: full or basic diagnostic result based on plan.
    """
    from models.user import can_run_check, filter_result_by_plan, check_rate_limit, log_event

    data = request.get_json(force=True)
    user_input = data.get("input", "").strip()
    user_id = g.user_id

    if not user_input:
        return jsonify({"error": "Please describe what's going on with your car."}), 400

    # Rate limit check
    if not check_rate_limit(request.remote_addr):
        return jsonify({
            "error": "Too many requests. Please wait 20 seconds between checks.",
            "rate_limited": True,
        }), 429

    # Check gate — deducts a check or blocks
    gate = can_run_check(user_id)
    if not gate["allowed"]:
        log_event("check_blocked", user_id, {"reason": "no_checks_remaining"})
        return jsonify({
            "status": "locked",
            "message": gate["message"],
            "upgrade_required": gate.get("upgrade_required", False),
            "addon_available": gate.get("addon_available", False),
            "checks_remaining": 0,
            "upgrade_url": "/api/v1/billing/upgrade",
        }), 403

    log_event("check_used", user_id)

    _load_data()

    # Strategy 1: Direct DTC code
    if _is_dtc_code(user_input):
        code = user_input.upper()
        result = _build_result_for_code(code)
        results = _enhance_with_claspion_verification([result], user_input)
        raw = {"input": user_input, "input_type": "dtc_code", "results": results}
        filtered = filter_result_by_plan(raw, gate["plan"])
        filtered["checks_remaining"] = gate["checks_remaining"]
        return jsonify(filtered)

    # Strategy 2: Extract codes from text
    extracted = _extract_codes(user_input)
    if extracted:
        results = [_build_result_for_code(c) for c in extracted[:3]]
        results = _enhance_with_claspion_verification(results, user_input)
        raw = {"input": user_input, "input_type": "codes_in_text", "results": results}
        filtered = filter_result_by_plan(raw, gate["plan"])
        filtered["checks_remaining"] = gate["checks_remaining"]
        return jsonify(filtered)

    # Strategy 3: Symptom matching
    matched_codes = _match_symptoms(user_input)
    results = [_build_result_for_code(c) for c in matched_codes[:2]]
    results = _enhance_with_claspion_verification(results, user_input)
    raw = {
        "input": user_input, "input_type": "symptoms",
        "note": "Based on your description, here are the most likely issues:",
        "results": results,
    }
    filtered = filter_result_by_plan(raw, gate["plan"])
    filtered["checks_remaining"] = gate["checks_remaining"]
    return jsonify(filtered)


@quick_check_bp.route("/demos", methods=["GET"])
@require_auth
def get_demos():
    """Return available demo scenarios."""
    return jsonify({"demos": list(DEMOS.values())})


@quick_check_bp.route("/demo/<demo_id>", methods=["GET"])
@require_auth
def run_demo(demo_id):
    """Run a preloaded demo scenario."""
    demo = DEMOS.get(demo_id.lower())
    if not demo:
        return jsonify({"error": "Demo not found"}), 404

    _load_data()
    user_input = demo["input"]

    if _is_dtc_code(user_input):
        result = _build_result_for_code(user_input.upper())
        results = _enhance_with_claspion_verification([result], user_input)
        return jsonify({
            "input": user_input,
            "input_type": "demo",
            "demo": demo,
            "results": results
        })

    matched_codes = _match_symptoms(user_input)
    results = [_build_result_for_code(c) for c in matched_codes[:2]]
    return jsonify({
        "input": user_input,
        "input_type": "demo",
        "demo": demo,
        "results": results
    })
