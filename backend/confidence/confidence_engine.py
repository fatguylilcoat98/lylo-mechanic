"""
The Good Neighbor Guard — LYLO Mechanic
Christopher Hughes · Sacramento, CA
AI Collaborators: Claude · GPT · Gemini · Groq
Truth · Safety · We Got Your Back

Data confidence engine: computes overall diagnostic confidence
from session quality signals.
"""

from models.schemas import VehicleState, SymptomIntake, DataConfidence
from normalization.normalizer import get_pid_value


def compute_confidence(
    state: VehicleState,
    symptoms: SymptomIntake | None,
) -> DataConfidence:
    """
    Compute DataConfidence from VehicleState and optional symptoms.
    Confidence starts at 1.0 and is progressively downgraded.
    """
    score = 1.0
    reasons = []
    blocked_outputs = []

    flags = set(state.session_flags)

    # ── Connection quality ──────────────────────────────────────────
    if state.connection_quality == "dropped":
        score -= 0.40
        reasons.append("OBD adapter connection was dropped during read")
        blocked_outputs.append("diagnosis")
    elif state.connection_quality == "unstable":
        score -= 0.20
        reasons.append("OBD adapter connection was unstable")

    # ── Read completeness ───────────────────────────────────────────
    if not state.read_complete or "INCOMPLETE_READ" in flags:
        score -= 0.25
        reasons.append("OBD read cycle did not complete successfully")
        blocked_outputs.append("high_confidence_diagnosis")

    # ── Codes cleared ───────────────────────────────────────────────
    if "CODES_POSSIBLY_CLEARED" in flags:
        score -= 0.20
        reasons.append("Fault codes may have been cleared before scan — active faults could be missing")

    # ── Monitors incomplete ─────────────────────────────────────────
    monitors_incomplete = any(
        m.status == "incomplete" for m in state.readiness_monitors
    )
    if "MONITORS_INCOMPLETE" in flags or monitors_incomplete:
        score -= 0.15
        reasons.append("One or more readiness monitors have not completed — system self-tests are pending")

    # ── PID coverage ────────────────────────────────────────────────
    total_pids = len(state.pids)
    missing_pids = sum(1 for p in state.pids if p.is_missing or p.is_unsupported)
    implausible_pids = sum(1 for p in state.pids if p.is_implausible)

    if total_pids == 0:
        pid_coverage = "limited"
        score -= 0.15
        reasons.append("No live sensor data available")
    elif missing_pids / max(total_pids, 1) > 0.5:
        pid_coverage = "limited"
        score -= 0.10
        reasons.append("More than half of requested sensor values are unavailable")
    elif missing_pids > 0:
        pid_coverage = "partial"
        score -= 0.05
    else:
        pid_coverage = "full"

    if implausible_pids > 0:
        score -= 0.10 * implausible_pids
        reasons.append(f"{implausible_pids} sensor reading(s) returned physically impossible values and were discarded")

    # ── Manufacturer-specific unknowns ──────────────────────────────
    mfr_specific = [d for d in state.dtcs if d.category == "manufacturer_specific"]
    has_mfr_unknowns = len(mfr_specific) > 0
    if has_mfr_unknowns:
        score -= 0.10
        reasons.append(f"{len(mfr_specific)} manufacturer-specific code(s) present — exact interpretation requires make/model service data")

    # ── Symptom alignment ───────────────────────────────────────────
    alignment = "no_symptoms"
    if symptoms:
        alignment = _check_symptom_alignment(state, symptoms)
        if alignment == "conflicting":
            score -= 0.15
            reasons.append("User-reported symptoms conflict with available sensor data — physical inspection needed")

    # ── Cascade codes ───────────────────────────────────────────────
    cascade_codes = [d for d in state.dtcs if d.cascade_candidate]
    if cascade_codes:
        score -= 0.05
        reasons.append(f"{len(cascade_codes)} code(s) may be downstream effects of a root cause — do not chase individually")

    # ── No-code symptom case ────────────────────────────────────────
    if symptoms and not state.dtcs and symptoms.primary_category not in ("warning_light_only", None):
        score -= 0.10
        reasons.append("No fault codes detected but symptoms are present — OBD-II cannot detect all failure types")
        blocked_outputs.append("code_based_diagnosis")

    # ── Floor confidence ────────────────────────────────────────────
    score = max(0.0, min(1.0, score))

    # ── Determine blocked outputs ───────────────────────────────────
    if score < 0.35:
        blocked_outputs.append("cost_estimate")
        if "diagnosis" not in blocked_outputs:
            blocked_outputs.append("high_confidence_diagnosis")

    limit_reason = "; ".join(reasons) if reasons else None

    return DataConfidence(
        connection_valid=state.connection_quality != "dropped",
        read_complete=state.read_complete,
        pid_coverage=pid_coverage,
        symptom_alignment=alignment,
        codes_possibly_cleared="CODES_POSSIBLY_CLEARED" in flags,
        monitors_incomplete=monitors_incomplete,
        unstable_session=state.connection_quality in ("unstable", "dropped"),
        manufacturer_specific_unknowns=has_mfr_unknowns,
        overall=round(score, 2),
        limit_reason=limit_reason,
        blocked_outputs=list(set(blocked_outputs)),
    )


def _check_symptom_alignment(state: VehicleState, symptoms: SymptomIntake) -> str:
    """
    Cross-check symptoms against available sensor data.
    Returns 'consistent', 'conflicting', or 'neutral'.
    """
    conflicts = 0
    consistencies = 0

    cat = symptoms.primary_category

    # Overheating symptom vs coolant temp sensor
    if cat == "overheating":
        coolant = get_pid_value(state, "ENGINE_COOLANT_TEMP")
        if coolant is not None:
            if coolant < 200:
                conflicts += 1  # User says overheating but sensor reads normal
            else:
                consistencies += 1

    # Rough idle symptom vs engine load / fuel trims
    if cat in ("rough_idle", "misfire"):
        ltft = get_pid_value(state, "LONG_TERM_FUEL_TRIM_B1")
        if ltft is not None:
            if abs(ltft) > 10:
                consistencies += 1
        misfire_codes = [d for d in state.dtcs if d.code.startswith("P030")]
        if misfire_codes:
            consistencies += 1

    # Electrical symptom vs battery voltage
    if cat == "electrical":
        voltage = get_pid_value(state, "BATTERY_VOLTAGE")
        if voltage is not None:
            if voltage < 13.0:
                consistencies += 1

    # No-code brake symptom with clean data
    if cat == "brake_issue":
        brake_codes = [d for d in state.dtcs if d.system == "chassis"]
        if not brake_codes:
            # No codes but brake symptom — neutral (OBD can't see brakes in most cases)
            return "neutral"

    if conflicts > consistencies:
        return "conflicting"
    elif consistencies > 0:
        return "consistent"
    return "neutral"
