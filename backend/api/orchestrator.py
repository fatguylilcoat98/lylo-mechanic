"""
The Good Neighbor Guard — LYLO Mechanic
Christopher Hughes · Sacramento, CA
AI Collaborators: Claude · GPT · Gemini · Groq
Truth · Safety · We Got Your Back

Main diagnostic orchestrator: runs all layers in sequence
and assembles the final MechanicResponse.
"""

import uuid
from models.schemas import (
    OBDSessionInput, SymptomIntake, MechanicResponse,
    DIYEligibility
)
from normalization.normalizer import normalize_session
from confidence.confidence_engine import compute_confidence
from diagnosis.hypothesis_engine import generate_hypotheses, build_what_we_know
from safety.safety_classifier import classify_safety
from diy.eligibility_gate import evaluate_diy_eligibility
from cost.cost_engine import build_cost_estimates
from veracore.truth_check import run_truth_check
from handshake.client import classify as handshake_classify, get_friction_response


def run_diagnosis(
    session_input: OBDSessionInput,
    symptoms: SymptomIntake | None = None,
    extra_flags: list[str] | None = None,
) -> MechanicResponse:
    """
    Full diagnostic pipeline.
    Runs all 12 layers in order and returns MechanicResponse.
    """
    session_id = str(uuid.uuid4())[:8].upper()

    # ── Layer 1 & 2: Ingest + Normalize ───────────────────────────
    state = normalize_session(session_input)

    # Inject any extra flags (e.g. FLASHING_MIL from demo)
    if extra_flags:
        state.session_flags.extend(extra_flags)

    # ── Layer 3: Data Confidence ───────────────────────────────────
    confidence = compute_confidence(state, symptoms)

    # ── Layer 4 & 5: Symptoms already structured; note important PIDs
    # (symptom-to-PID mapping is embedded in hypothesis engine)

    # ── Layer 6: Hypothesis Engine ─────────────────────────────────
    hypotheses, check_first, cascade_notes = generate_hypotheses(state, symptoms, confidence)
    what_we_know = build_what_we_know(state, confidence)

    # ── Layer 7: Safety Escalation ─────────────────────────────────
    safety = classify_safety(state, symptoms)

    # ── Layer 8: DIY Gate — for top hypothesis only initially ──────
    diy_eligibility = None
    if hypotheses and not safety.is_drive_blocking():
        top_cause_id = hypotheses[0].cause_id
        diy_eligibility = evaluate_diy_eligibility(
            top_cause_id,
            state.vehicle,
            safety,
        )

    # ── Layer 9: Cost Engine ───────────────────────────────────────
    cost_estimates = build_cost_estimates(hypotheses[:3], confidence)

    # ── Layer 10: Tutorial Gate ────────────────────────────────────
    tutorial_available, tutorial_blocked_reason = _evaluate_tutorial_gate(
        safety, diy_eligibility, confidence
    )

    # ── Layer 11: Veracore Truth Check ─────────────────────────────
    veracore_flags = run_truth_check(hypotheses, confidence, safety, cost_estimates)

    # ── Layer 12: Handshake Check ──────────────────────────────────
    # Build a question summary for the Handshake from the top hypothesis
    _hs_question = ""
    if hypotheses:
        _hs_question = f"Vehicle repair: {hypotheses[0].cause_name} — {safety.level}"
    handshake_required, handshake_reason, handshake_api = _evaluate_handshake(
        safety, diy_eligibility, _hs_question
    )

    # ── Build final narrative ─────────────────────────────────────
    what_this_might_mean = _build_meaning_narrative(hypotheses, confidence, cascade_notes)
    professional_triggers = _build_professional_triggers(safety, hypotheses, state)

    return MechanicResponse(
        session_id=session_id,
        vehicle=state.vehicle,
        confidence=confidence,
        safety=safety,
        hypotheses=hypotheses,
        diy_eligibility=diy_eligibility,
        cost_estimates=cost_estimates,
        tutorial_available=tutorial_available,
        tutorial_blocked_reason=tutorial_blocked_reason,
        veracore_flags=veracore_flags,
        handshake_required=handshake_required,
        handshake_reason=handshake_reason,
        handshake_api=handshake_api,
        what_we_know=what_we_know,
        what_this_might_mean=what_this_might_mean,
        what_to_check_first=check_first,
        professional_help_triggers=professional_triggers,
        session_flags=state.session_flags,
    )


def _evaluate_tutorial_gate(
    safety, diy: DIYEligibility | None, confidence
) -> tuple[bool, str | None]:
    if safety.is_drive_blocking():
        return False, "Vehicle is not safe to drive. Resolve safety issue before attempting any repair."
    if diy is None:
        return False, "No DIY assessment available."
    if diy.hard_stop:
        return False, diy.hard_stop_reason
    if diy.verdict in ("DANGEROUS_TO_ATTEMPT", "PROFESSIONAL_ONLY"):
        return False, f"This repair requires professional handling: {diy.hard_stop_reason or diy.verdict}"
    if confidence.overall < 0.45:
        return False, "Diagnosis confidence is too low to safely guide a repair. Physical inspection needed first."
    return True, None


def _evaluate_handshake(safety, diy: DIYEligibility | None, question: str = "") -> tuple[bool, str | None, dict | None]:
    """
    Layer 12: Handshake evaluation.
    First checks local rules. If high-stakes, also calls The Handshake API
    at the-handshake.onrender.com for external friction classification.
    Returns (required, reason, handshake_api_result).
    """
    required = False
    reason = None

    if safety.user_must_acknowledge:
        required = True
        reason = f"Safety classification requires acknowledgment: {safety.level}"
    elif diy and diy.verdict == "DIY_WITH_CAUTION":
        required = True
        reason = "This repair has caution steps that require your acknowledgment before proceeding."
    elif safety.level in ("DO_NOT_DRIVE", "TOW_RECOMMENDED", "EMERGENCY_STOP_IMMEDIATELY"):
        required = True
        reason = "High-risk safety condition requires your confirmation that you understand the risks."

    # Call The Handshake API for external friction classification
    hs_api = None
    if required and question:
        hs_result = handshake_classify(question)
        hs_api = get_friction_response(hs_result)

    return required, reason, hs_api


def _build_meaning_narrative(hypotheses, confidence, cascade_notes) -> str:
    if not hypotheses:
        return "No diagnostic data is available to form a conclusion. A physical inspection is recommended."

    top = hypotheses[0]
    confidence_label = confidence.label()

    intro = f"Based on {confidence_label.lower()} confidence scan data, the most likely cause is '{top.cause_name}' ({top.confidence_score}% confidence)."

    if len(hypotheses) > 1:
        second = hypotheses[1]
        spread = top.confidence_score - second.confidence_score
        if spread < 15:
            intro += f" However, '{second.cause_name}' is nearly as likely ({second.confidence_score}%) — do not rule it out without physical inspection."

    if cascade_notes:
        intro += " " + cascade_notes[0]

    if confidence.codes_possibly_cleared:
        intro += " Note: codes may have been recently cleared — the fault that triggered this code may not yet have re-appeared."

    return intro


def _build_professional_triggers(safety, hypotheses, state) -> list[str]:
    triggers = []

    if safety.is_drive_blocking():
        triggers.append(f"Vehicle safety classification is {safety.level} — do not drive to a shop, call for a tow")

    if any(d.code in {"P0011", "P0021"} for d in state.dtcs) and any(
        "engine_knock" in (h.supporting_evidence or []) for h in hypotheses
    ):
        triggers.append("Cam timing fault with engine noise — potential timing chain failure, do not delay")

    if any(d.code == "P0217" for d in state.dtcs):
        triggers.append("Engine over-temperature code — overheating can cause permanent engine damage quickly")

    oil_codes = {"P0520", "P0521", "P0522"}
    if {d.code for d in state.dtcs} & oil_codes:
        triggers.append("Oil pressure fault — stop engine immediately, do not restart until inspected")

    if any(d.category == "manufacturer_specific" for d in state.dtcs):
        triggers.append("Manufacturer-specific codes present — require make/model-specific scan tool for accurate diagnosis")

    if not triggers:
        triggers.append("If symptoms worsen or a new warning light appears, stop driving and seek professional inspection")

    return triggers
