"""
The Good Neighbor Guard — LYLO Mechanic
Christopher Hughes · Sacramento, CA
AI Collaborators: Claude · GPT · Gemini · Groq
Truth · Safety · We Got Your Back

Hypothesis engine: generates multi-cause ranked diagnosis.
Never single-code single-fix.
"""

import json
import os
from typing import List, Optional
from models.schemas import (
    VehicleState, SymptomIntake, DataConfidence,
    DiagnosisHypothesis
)
from normalization.normalizer import get_pid_value

_RULES_PATH = os.path.join(os.path.dirname(__file__), "../data/hypothesis_rules/cause_map.json")
_RULES: dict = {}


def _load_rules():
    global _RULES
    if not _RULES:
        with open(_RULES_PATH) as f:
            _RULES = json.load(f)


def generate_hypotheses(
    state: VehicleState,
    symptoms: SymptomIntake | None,
    confidence: DataConfidence,
) -> tuple[List[DiagnosisHypothesis], List[str], List[str]]:
    """
    Generate ranked hypotheses from DTC codes and symptoms.
    Returns: (hypotheses, check_first_steps, cascade_notes)
    """
    _load_rules()

    all_hypotheses = []
    check_first = []
    cascade_notes = []
    codes_processed = set()

    active_codes = [d for d in state.dtcs if d.status == "active"]

    # ── Process each active DTC ────────────────────────────────────
    for dtc in active_codes:
        rule = _RULES.get(dtc.code)
        if not rule:
            # No rule available — still surface the code as low-confidence
            all_hypotheses.append(_unknown_code_hypothesis(dtc))
            continue

        if dtc.cascade_candidate:
            cascade_notes.append(
                f"{dtc.code}: May be a cascade fault triggered by another code. "
                "Investigate root cause codes first before addressing this one."
            )

        for cause_data in rule["causes"]:
            hyp = _build_hypothesis(cause_data, state, symptoms, confidence, dtc.code)
            all_hypotheses.append(hyp)

        if rule.get("check_first"):
            check_first.extend(rule["check_first"])

        if rule.get("cascade_note"):
            cascade_notes.append(rule["cascade_note"])

        codes_processed.add(dtc.code)

    # ── Symptom-only diagnosis (no codes) ──────────────────────────
    if not active_codes and symptoms:
        symptom_hyps, symptom_checks = _symptom_only_hypotheses(state, symptoms, confidence)
        all_hypotheses.extend(symptom_hyps)
        check_first.extend(symptom_checks)

    # ── Deduplicate and rank ───────────────────────────────────────
    seen_ids = set()
    unique_hyps = []
    for h in all_hypotheses:
        if h.cause_id not in seen_ids:
            seen_ids.add(h.cause_id)
            unique_hyps.append(h)

    # Sort by confidence descending
    unique_hyps.sort(key=lambda h: h.confidence_score, reverse=True)

    # Apply confidence cap from data confidence
    unique_hyps = _apply_confidence_cap(unique_hyps, confidence)

    # Assign final ranks
    for i, h in enumerate(unique_hyps):
        h.cause_rank = i + 1

    return unique_hyps, list(dict.fromkeys(check_first)), cascade_notes


def _build_hypothesis(
    cause_data: dict,
    state: VehicleState,
    symptoms: SymptomIntake | None,
    confidence: DataConfidence,
    trigger_code: str,
) -> DiagnosisHypothesis:
    base_score = cause_data["base_confidence"]
    boosters = cause_data.get("boosted_by", [])
    boost_applied = []

    # Apply boost signals
    for booster in boosters:
        if _check_booster(booster, state, symptoms):
            base_score = min(95, base_score + 12)
            boost_applied.append(booster)

    # Build supporting evidence
    evidence = list(cause_data.get("supporting_evidence_template", []))
    if boost_applied:
        evidence.append(f"Boosted by: {', '.join(b.replace('_', ' ') for b in boost_applied)}")

    # Add live data evidence
    ltft = get_pid_value(state, "LONG_TERM_FUEL_TRIM_B1")
    if ltft is not None and abs(ltft) > 10:
        evidence.append(f"Long-term fuel trim is {ltft:+.1f}% — elevated, indicating lean/rich condition")

    coolant = get_pid_value(state, "ENGINE_COOLANT_TEMP")
    if coolant is not None and coolant > 225:
        evidence.append(f"Coolant temperature elevated: {coolant:.0f}°F")

    return DiagnosisHypothesis(
        cause_rank=0,  # set after sorting
        cause_id=cause_data["id"],
        cause_name=cause_data["name"],
        cause_description=cause_data["description"],
        confidence_score=int(base_score),
        confidence_basis=cause_data["basis"],
        supporting_evidence=evidence,
        what_could_make_this_wrong=cause_data.get("what_could_be_wrong", []),
        is_downstream=cause_data.get("is_downstream", False),
        probable_root_cause_id=cause_data.get("probable_root_cause_id"),
        requires_physical_inspection=True,
    )


def _check_booster(booster: str, state: VehicleState, symptoms: SymptomIntake | None) -> bool:
    """Check if a confidence booster condition is met."""
    symptom_cat = symptoms.primary_category.lower() if symptoms else ""
    symptom_subs = [s.lower() for s in (symptoms.subcategories if symptoms else [])]
    odometer = state.vehicle.odometer or 0

    booster_map = {
        "high_mileage": odometer > 80000,
        "high_mileage_over_150k": odometer > 150000,
        "rough_idle": symptom_cat in ("rough_idle", "misfire") or "rough_idle" in symptom_subs,
        "hesitation": symptom_cat == "hesitation" or "hesitation" in symptom_subs,
        "symptom_warning_light_only": symptom_cat == "warning_light_only",
        "misfire_under_load": "misfire_load" in symptom_subs,
        "misfire_worse_when_hot": "worse_when_hot" in symptom_subs,
        "symptom_stalling": symptom_cat == "stalling",
        "cold_start_rattle": "cold_start_rattle" in symptom_subs,
        "symptom_electrical": symptom_cat == "electrical",
        "symptom_exhaust_smell": "exhaust_smell" in symptom_subs,
        "symptom_ticking_noise_cold": "ticking_cold" in symptom_subs,
        "vibration_highway": symptom_cat == "vibration" and "highway" in (symptoms.when_it_happens if symptoms else []),
        "vibration_steering_wheel": "steering_wheel_vibration" in symptom_subs,
        "vibration_changes_with_turns": "vibration_turns" in symptom_subs,
        "humming_noise": "humming" in symptom_subs,
        "vibration_acceleration": "vibration_acceleration" in symptom_subs,
        "clunking_turning": "clunking_turning" in symptom_subs,
        "symptom_brake_squeal": "squeal" in symptom_subs,
        "symptom_soft_pedal": "soft_pedal" in symptom_subs,
        "symptom_pedal_to_floor": "pedal_to_floor" in symptom_subs,
        "multiple_unrelated_codes": len(state.dtcs) > 3,
        "recent_oil_change": "recent_oil_change" in symptom_subs,
        "no_prior_cam_codes": not any(c.code in ("P0011", "P0021") for c in state.dtcs if c.status == "history"),
        "prior_misfires": any(c.code.startswith("P030") for c in state.dtcs),
        "prior_oil_burning": "oil_burning" in symptom_subs,
        "correct_oil_confirmed": "correct_oil" in symptom_subs,
        "hesitation_acceleration": symptom_cat == "hesitation" and "under_load" in (symptoms.when_it_happens if symptoms else []),
    }

    # Live data boosters
    ltft = get_pid_value(state, "LONG_TERM_FUEL_TRIM_B1")
    maf = get_pid_value(state, "MAF_AIR_FLOW_RATE")
    voltage = get_pid_value(state, "BATTERY_VOLTAGE")

    booster_map["high_ltft"] = ltft is not None and ltft > 10
    booster_map["high_ltft_over_10"] = ltft is not None and ltft > 10
    booster_map["high_ltft_or_stft"] = ltft is not None and abs(ltft) > 8
    booster_map["low_maf_reading"] = maf is not None and maf < 2.0
    booster_map["battery_voltage_pid_low"] = voltage is not None and voltage < 13.0

    return booster_map.get(booster, False)


def _symptom_only_hypotheses(
    state: VehicleState,
    symptoms: SymptomIntake,
    confidence: DataConfidence,
) -> tuple[List[DiagnosisHypothesis], List[str]]:
    """Generate hypotheses when no codes are present — symptom-only path."""
    cat = symptoms.primary_category.lower()

    symptom_rule_map = {
        "vibration": "NO_CODE_VIBRATION",
        "brake_issue": "NO_CODE_BRAKE",
    }

    rule_key = symptom_rule_map.get(cat)
    if not rule_key or rule_key not in _RULES:
        return [], []

    rule = _RULES[rule_key]
    hypotheses = []
    for cause_data in rule["causes"]:
        hyp = _build_hypothesis(cause_data, state, symptoms, confidence, "SYMPTOM_ONLY")
        # Symptom-only diagnoses get a confidence penalty
        hyp.confidence_score = max(20, hyp.confidence_score - 15)
        hyp.confidence_basis = "symptom_correlated"
        hypotheses.append(hyp)

    return hypotheses, rule.get("check_first", [])


def _unknown_code_hypothesis(dtc) -> DiagnosisHypothesis:
    return DiagnosisHypothesis(
        cause_rank=99,
        cause_id=f"unknown_{dtc.code.lower()}",
        cause_name=f"Unknown fault: {dtc.code}",
        cause_description=dtc.description,
        confidence_score=20,
        confidence_basis="low_confidence",
        supporting_evidence=[f"Code {dtc.code} is present but no interpretation rules are available"],
        what_could_make_this_wrong=["This code requires make/model specific service data to interpret accurately"],
        is_downstream=False,
        requires_physical_inspection=True,
    )


def _apply_confidence_cap(
    hypotheses: List[DiagnosisHypothesis],
    confidence: DataConfidence,
) -> List[DiagnosisHypothesis]:
    """
    Cap confidence scores based on data quality.
    Cannot have high confidence in a diagnosis when the underlying data is weak.
    """
    max_score = 95
    if confidence.overall < 0.50:
        max_score = 60
    elif confidence.overall < 0.70:
        max_score = 75

    for h in hypotheses:
        if h.confidence_score > max_score:
            h.confidence_score = max_score
            h.what_could_make_this_wrong.append(
                f"Confidence capped at {max_score}% due to incomplete scan data — physical inspection needed to confirm"
            )
    return hypotheses


def build_what_we_know(state: VehicleState, confidence: DataConfidence) -> List[str]:
    """Generate the 'what we know' list from confirmed OBD data."""
    known = []

    active = [d for d in state.dtcs if d.status == "active"]
    pending = [d for d in state.dtcs if d.status == "pending"]

    for dtc in active:
        known.append(f"Active fault: {dtc.code} — {dtc.description}")

    for dtc in pending:
        known.append(f"Pending fault (not yet confirmed): {dtc.code} — {dtc.description}")

    ltft = get_pid_value(state, "LONG_TERM_FUEL_TRIM_B1")
    if ltft is not None:
        if abs(ltft) > 10:
            known.append(f"Long-term fuel trim Bank 1: {ltft:+.1f}% — significantly {'lean' if ltft > 0 else 'rich'}")
        else:
            known.append(f"Fuel trim Bank 1: {ltft:+.1f}% — within normal range")

    coolant = get_pid_value(state, "ENGINE_COOLANT_TEMP")
    if coolant is not None:
        status = "normal" if 160 <= coolant <= 220 else ("elevated" if coolant > 220 else "below normal")
        known.append(f"Coolant temperature: {coolant:.0f}°F — {status}")

    voltage = get_pid_value(state, "BATTERY_VOLTAGE")
    if voltage is not None:
        status = "normal" if 13.5 <= voltage <= 14.8 else ("low — may indicate battery/alternator issue" if voltage < 13.5 else "high")
        known.append(f"Battery/charging voltage: {voltage:.1f}V — {status}")

    monitors_incomplete = [m.name for m in state.readiness_monitors if m.status == "incomplete"]
    if monitors_incomplete:
        known.append(f"Readiness monitors not yet complete: {', '.join(monitors_incomplete)}")

    if "CODES_POSSIBLY_CLEARED" in state.session_flags:
        known.append("⚠ Codes may have been cleared before this scan — some faults may not yet have re-triggered")

    if not active and not pending:
        known.append("No active or pending fault codes detected")

    return known
