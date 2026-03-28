"""
The Good Neighbor Guard — LYLO Mechanic
Christopher Hughes · Sacramento, CA
AI Collaborators: Claude · GPT · Gemini · Groq
Truth · Safety · We Got Your Back

Safety escalation matrix: pure decision function.
Highest severity wins. Symptom overrides sensor on safety-critical categories.
"""

from models.schemas import VehicleState, SymptomIntake, SafetyClassification
from normalization.normalizer import get_pid_value


def classify_safety(
    state: VehicleState,
    symptoms: SymptomIntake | None,
) -> SafetyClassification:
    """
    Evaluate all conditions and return the highest-severity safety classification.
    Rules are evaluated in order from most to least severe.
    Highest match wins.
    """
    codes = {d.code for d in state.dtcs if d.status == "active"}
    symptom_cat = symptoms.primary_category.lower() if symptoms else ""
    symptom_subs = [s.lower() for s in (symptoms.subcategories if symptoms else [])]
    symptom_severity = symptoms.severity if symptoms else "minor"

    all_conditions = []
    symptom_override = False

    # ── EMERGENCY / STOP IMMEDIATELY ─────────────────────────────────
    emergency_conditions = []

    oil_pressure_codes = {"P0520", "P0521", "P0522", "P0523"}
    if oil_pressure_codes & codes:
        emergency_conditions.append("Oil pressure fault detected — engine damage risk if driven")

    coolant_temp = get_pid_value(state, "ENGINE_COOLANT_TEMP")
    if coolant_temp is not None and coolant_temp >= 240:
        emergency_conditions.append(f"Coolant temperature critical: {coolant_temp:.0f}°F")

    if symptom_cat == "overheating" and symptom_severity == "severe":
        emergency_conditions.append("User reports severe overheating")
        symptom_override = True

    if "pedal_to_floor" in symptom_subs or (
        symptom_cat == "brake_issue" and symptom_severity == "severe"
        and "no_brake_response" in symptom_subs
    ):
        emergency_conditions.append("Brake pedal failure reported — do not drive under any circumstances")
        symptom_override = True

    if "smoke_from_engine" in symptom_subs or (
        symptom_cat == "smoke" and symptom_severity in ("significant", "severe")
    ):
        emergency_conditions.append("Engine smoke reported — possible fire risk")
        symptom_override = True

    if emergency_conditions:
        return SafetyClassification(
            level="EMERGENCY_STOP_IMMEDIATELY",
            triggering_conditions=emergency_conditions,
            reasoning="One or more conditions require immediate stop. Do not attempt to drive to a shop.",
            symptom_overrides_sensor=symptom_override,
            user_must_acknowledge=True,
        )

    # ── TOW RECOMMENDED ───────────────────────────────────────────────
    tow_conditions = []

    flashing_mil = "FLASHING_MIL" in state.session_flags
    has_misfire = any(c.startswith("P030") for c in codes)
    has_p0420 = "P0420" in codes

    if flashing_mil or (has_misfire and has_p0420):
        tow_conditions.append("Active misfire with catalyst fault — catalyst damage risk is high")

    cam_timing_codes = {"P0011", "P0021", "P0012", "P0022"}
    if cam_timing_codes & codes and "engine_knock" in symptom_subs:
        tow_conditions.append("Cam timing fault with reported engine knock — potential timing chain failure")

    if "P0217" in codes:
        tow_conditions.append("Engine over-temperature code active")

    brake_codes = {c for c in codes if c.startswith("C0")}
    if brake_codes and symptom_cat == "brake_issue":
        tow_conditions.append("Brake system fault code with reported brake symptoms")

    trans_codes = {c for c in codes if c.startswith("P07") or c.startswith("P08")}
    if trans_codes and "transmission_slip" in symptom_subs:
        tow_conditions.append("Transmission fault code with reported slipping")

    if symptom_cat == "overheating" and symptom_severity in ("significant", "severe"):
        tow_conditions.append("Significant overheating reported")
        symptom_override = True

    if tow_conditions:
        return SafetyClassification(
            level="TOW_RECOMMENDED",
            triggering_conditions=tow_conditions,
            reasoning="Driving this vehicle poses a significant risk of major damage or unsafe operation.",
            symptom_overrides_sensor=symptom_override,
            user_must_acknowledge=True,
        )

    # ── DO NOT DRIVE ──────────────────────────────────────────────────
    dnd_conditions = []

    if flashing_mil and not tow_conditions:
        dnd_conditions.append("Flashing check engine light indicates active misfire — catalyst damage in progress")

    airbag_codes = {c for c in codes if c.startswith("B") and "00" in c}
    if airbag_codes:
        dnd_conditions.append("SRS/Airbag fault active — supplemental restraint system may be compromised")

    abs_codes = {c for c in codes if c.startswith("C")}
    if abs_codes and (symptom_cat == "brake_issue" or "abs_light" in symptom_subs):
        dnd_conditions.append("ABS/Chassis fault with brake symptom — anti-lock system may not function")

    if state.vehicle.is_hybrid or state.vehicle.is_ev:
        hv_codes = {c for c in codes if c.startswith("P1") and "hv" in c.lower()}
        if hv_codes or "hv_warning" in symptom_subs:
            dnd_conditions.append("High-voltage system fault on hybrid/EV — do not drive")

    cam_timing_codes2 = {"P0011", "P0021"}
    if cam_timing_codes2 & codes and symptom_severity in ("significant", "severe"):
        dnd_conditions.append("Cam timing fault with significant symptoms — timing chain risk")

    if symptom_cat == "brake_issue" and "soft_pedal" in symptom_subs:
        dnd_conditions.append("Soft brake pedal reported — do not drive until hydraulic system inspected")
        symptom_override = True

    if dnd_conditions:
        return SafetyClassification(
            level="DO_NOT_DRIVE",
            triggering_conditions=dnd_conditions,
            reasoning="This vehicle should not be driven until the identified issues are resolved.",
            symptom_overrides_sensor=symptom_override,
            user_must_acknowledge=True,
        )

    # ── INSPECT SOON ──────────────────────────────────────────────────
    inspect_conditions = []

    if has_misfire and not has_p0420 and not flashing_mil:
        if symptom_severity in ("noticeable", "significant"):
            inspect_conditions.append("Active misfire — schedule inspection within 2–3 days")
        else:
            inspect_conditions.append("Misfire code active — intermittent, but needs attention soon")

    cam_timing_mild = cam_timing_codes & codes
    if cam_timing_mild and symptom_severity in ("minor", "noticeable"):
        inspect_conditions.append("Cam timing fault — inspect within 1 week")

    if "P0335" in codes:
        inspect_conditions.append("Crankshaft position sensor fault — vehicle may stall without warning")

    if symptom_cat in ("steering_issue",) and symptom_severity != "minor":
        inspect_conditions.append("Steering issue reported — inspect before extended driving")
        symptom_override = True

    if inspect_conditions:
        return SafetyClassification(
            level="INSPECT_SOON",
            triggering_conditions=inspect_conditions,
            reasoning="Vehicle can be driven with caution but needs professional inspection within a few days.",
            symptom_overrides_sensor=symptom_override,
            user_must_acknowledge=False,
        )

    # ── DRIVE SHORT DISTANCE ONLY ─────────────────────────────────────
    short_conditions = []

    evap_codes = {c for c in codes if c in ("P0440", "P0441", "P0442", "P0455", "P0456")}
    if evap_codes and not has_misfire:
        short_conditions.append("EVAP emission fault — not a safety concern, but schedule inspection")

    if has_misfire and symptom_severity == "minor":
        short_conditions.append("Intermittent misfire code — avoid highway driving until inspected")

    if coolant_temp and 225 <= coolant_temp < 240:
        short_conditions.append(f"Coolant temperature slightly elevated: {coolant_temp:.0f}°F — monitor closely")

    monitors_incomplete = any(m.status == "incomplete" for m in state.readiness_monitors)
    if monitors_incomplete and "CODES_POSSIBLY_CLEARED" in state.session_flags:
        short_conditions.append("Codes were recently cleared — readiness monitors need more drive cycles to complete")

    if short_conditions:
        return SafetyClassification(
            level="DRIVE_SHORT_DISTANCE_ONLY",
            triggering_conditions=short_conditions,
            reasoning="Vehicle is operable but has active faults. Limit driving and schedule service soon.",
            symptom_overrides_sensor=False,
            user_must_acknowledge=False,
        )

    # ── SAFE TO DRIVE ─────────────────────────────────────────────────
    safe_conditions = ["No safety-critical fault codes detected"]
    if not state.dtcs:
        safe_conditions.append("No active diagnostic trouble codes")
    if not symptoms or symptoms.primary_category == "warning_light_only":
        safe_conditions.append("No drivability symptoms reported")

    return SafetyClassification(
        level="SAFE_TO_DRIVE",
        triggering_conditions=safe_conditions,
        reasoning="No safety-critical conditions detected. Monitor for changes and schedule routine service as needed.",
        symptom_overrides_sensor=False,
        user_must_acknowledge=False,
    )
