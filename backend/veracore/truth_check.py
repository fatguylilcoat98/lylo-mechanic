"""
The Good Neighbor Guard — LYLO Mechanic
Christopher Hughes · Sacramento, CA
AI Collaborators: Claude · GPT · Gemini · Groq
Truth · Safety · We Got Your Back

Veracore truth check: challenges the diagnosis before it reaches the user.
Flags weak evidence, overconfident claims, and unsupported recommendations.
"""

from typing import List
from models.schemas import (
    DiagnosisHypothesis, DataConfidence, SafetyClassification,
    RepairCostEstimate, VeracoreFlag
)


def run_truth_check(
    hypotheses: List[DiagnosisHypothesis],
    confidence: DataConfidence,
    safety: SafetyClassification,
    cost_estimates: List[RepairCostEstimate],
) -> List[VeracoreFlag]:
    """
    Challenge every significant claim in the diagnostic output.
    Return flags that should be surfaced to the user as honesty markers.
    """
    flags = []

    flags.extend(_check_overconfidence(hypotheses, confidence))
    flags.extend(_check_cascade_without_root(hypotheses))
    flags.extend(_check_single_cause_dominance(hypotheses))
    flags.extend(_check_cost_confidence(cost_estimates, confidence))
    flags.extend(_check_safety_without_evidence(safety, confidence))
    flags.extend(_check_manufacturer_specific(hypotheses))

    return flags


def _check_overconfidence(
    hypotheses: List[DiagnosisHypothesis],
    confidence: DataConfidence,
) -> List[VeracoreFlag]:
    flags = []
    for h in hypotheses:
        if h.confidence_score >= 75 and confidence.overall < 0.60:
            flags.append(VeracoreFlag(
                flag_type="overconfident",
                target=h.cause_id,
                message=(
                    f"'{h.cause_name}' is scored high confidence, but scan data quality is {confidence.label()}. "
                    "Physical inspection is required before treating this as confirmed."
                ),
                severity="caution",
            ))
        if h.confidence_basis == "low_confidence" and h.confidence_score > 50:
            flags.append(VeracoreFlag(
                flag_type="weak_evidence",
                target=h.cause_id,
                message=f"'{h.cause_name}' is marked low-confidence basis but scored {h.confidence_score}%. Do not present as probable.",
                severity="caution",
            ))
    return flags


def _check_cascade_without_root(hypotheses: List[DiagnosisHypothesis]) -> List[VeracoreFlag]:
    flags = []
    for h in hypotheses:
        if h.is_downstream and not h.probable_root_cause_id:
            flags.append(VeracoreFlag(
                flag_type="weak_evidence",
                target=h.cause_id,
                message=f"'{h.cause_name}' appears to be a downstream effect but no root cause has been identified. Chasing this repair first may not resolve the issue.",
                severity="caution",
            ))
    return flags


def _check_single_cause_dominance(hypotheses: List[DiagnosisHypothesis]) -> List[VeracoreFlag]:
    """Flag if top cause dominates too much — may indicate insufficient differential."""
    flags = []
    if len(hypotheses) >= 2:
        top = hypotheses[0].confidence_score
        second = hypotheses[1].confidence_score
        spread = top - second
        if spread < 10 and top > 60:
            flags.append(VeracoreFlag(
                flag_type="weak_evidence",
                target="diagnosis",
                message=(
                    f"Top two causes are within {spread}% of each other. "
                    "The diagnosis is uncertain — do not commit to the top cause without ruling out alternatives."
                ),
                severity="info",
            ))
    if len(hypotheses) == 1 and hypotheses[0].confidence_score > 70:
        flags.append(VeracoreFlag(
            flag_type="overconfident",
            target="diagnosis",
            message="Only one cause identified. Single-hypothesis diagnosis should be treated with caution — rule out alternatives before proceeding.",
            severity="caution",
        ))
    return flags


def _check_cost_confidence(
    cost_estimates: List[RepairCostEstimate],
    confidence: DataConfidence,
) -> List[VeracoreFlag]:
    flags = []
    for est in cost_estimates:
        if est.stale_warning:
            flags.append(VeracoreFlag(
                flag_type="stale_pricing",
                target=est.cause_id,
                message=f"Cost estimate for '{est.cause_id}' uses pricing data that is approaching expiration. Verify current parts pricing before purchasing.",
                severity="caution",
            ))
        if est.volatility == "HIGH" and confidence.overall < 0.60:
            flags.append(VeracoreFlag(
                flag_type="weak_evidence",
                target=est.cause_id,
                message=f"Cost estimate volatility is HIGH and diagnosis confidence is {confidence.label()}. Do not make purchasing decisions based on this estimate without professional confirmation.",
                severity="caution",
            ))
    return flags


def _check_safety_without_evidence(
    safety: SafetyClassification,
    confidence: DataConfidence,
) -> List[VeracoreFlag]:
    flags = []
    if safety.level in ("SAFE_TO_DRIVE", "DRIVE_SHORT_DISTANCE_ONLY") and confidence.overall < 0.40:
        flags.append(VeracoreFlag(
            flag_type="safety_concern",
            target="safety_classification",
            message=(
                "Vehicle is classified as drivable, but scan data confidence is very low. "
                "This classification may not reflect true vehicle condition. "
                "Consider professional inspection before extended driving."
            ),
            severity="critical",
        ))
    return flags


def _check_manufacturer_specific(hypotheses: List[DiagnosisHypothesis]) -> List[VeracoreFlag]:
    flags = []
    for h in hypotheses:
        if "manufacturer_specific" in h.cause_id or "unknown_" in h.cause_id:
            flags.append(VeracoreFlag(
                flag_type="weak_evidence",
                target=h.cause_id,
                message=f"'{h.cause_name}' involves a manufacturer-specific or unknown code. The interpretation shown is generic — consult make/model specific service data for accurate diagnosis.",
                severity="caution",
            ))
    return flags
