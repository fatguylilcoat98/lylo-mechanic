"""
Veracore — The Good Neighbor Guard
Built by Christopher Hughes · Sacramento, CA
Created with the help of AI collaborators (Claude · GPT · Gemini · Groq)
Truth · Safety · We Got Your Back

TRUTH DETECTOR — Vehicle Deception Analysis
Detects cleared codes, incomplete monitors, and data inconsistencies.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from enum import Enum
from datetime import datetime


class TruthStatus(Enum):
    CLEAN = "clean"                # Everything checks out
    INCONSISTENT = "inconsistent"  # Something does not add up
    UNCERTAIN = "uncertain"        # Not enough data to determine


class DeceptionSignal(Enum):
    CODES_RECENTLY_CLEARED = "codes_recently_cleared"
    MONITORS_INCOMPLETE = "monitors_incomplete"
    FUEL_TRIM_ANOMALY = "fuel_trim_anomaly"
    O2_SENSOR_FLAT = "o2_sensor_flat"
    MILEAGE_VS_WEAR_MISMATCH = "mileage_vs_wear_mismatch"
    PENDING_CODES_WITH_NO_STORED = "pending_codes_with_no_stored"
    FREEZE_FRAME_PRESENT_NO_CODES = "freeze_frame_present_no_codes"


@dataclass
class TruthSignal:
    """A single truth/deception signal found in the vehicle data."""
    signal: DeceptionSignal
    severity: str               # "low", "medium", "high"
    human_explanation: str      # Plain English — what this means
    raw_evidence: Optional[Dict] = None


@dataclass
class TruthReport:
    """Complete truth analysis of a vehicle scan."""
    status: TruthStatus
    signals: List[TruthSignal]
    headline: str               # One line summary
    detail: str                 # 2-3 sentence explanation
    confidence: float           # 0.0 to 1.0
    scanned_at: str
    recommendations: List[str]


def analyze_truth(obd_data: Dict[str, Any]) -> TruthReport:
    """
    Analyze OBD data for signs of deception or inconsistency.

    This is the core truth detection engine. It looks at:
    1. Were codes recently cleared? (time since clear + monitor status)
    2. Are readiness monitors complete? (incomplete = system hasnt verified itself)
    3. Do fuel trims make sense? (extreme values = hidden problem)
    4. Are O2 sensors behaving? (flat line = dead sensor)
    5. Are there pending codes with no stored codes? (problem exists but not confirmed yet)
    6. Is there freeze frame data but no active codes? (code was cleared after a fault)

    Args:
        obd_data: Dictionary containing:
            - dtcs: List of active diagnostic trouble codes
            - pending_dtcs: List of pending (unconfirmed) codes
            - monitors: Dict of readiness monitor statuses
            - fuel_trim_short: Short term fuel trim percentage
            - fuel_trim_long: Long term fuel trim percentage
            - o2_voltage: O2 sensor voltage reading
            - time_since_clear: Seconds since codes were last cleared (None if never)
            - freeze_frame: Freeze frame data (None if empty)
            - mileage: Current odometer reading (if available)
            - battery_voltage: Current battery voltage

    Returns:
        TruthReport with status, signals, and human-readable explanation
    """
    signals = []

    # === CHECK 1: Were codes recently cleared? ===
    time_since_clear = obd_data.get("time_since_clear")
    if time_since_clear is not None:
        # If codes were cleared within the last 50 miles of driving
        # (roughly 100-200 minutes of drive time), that is suspicious
        if time_since_clear < 12000:  # Less than ~200 minutes
            signals.append(TruthSignal(
                signal=DeceptionSignal.CODES_RECENTLY_CLEARED,
                severity="high",
                human_explanation=(
                    "The diagnostic codes on this vehicle were cleared recently. "
                    "This means someone erased the fault history. There may be "
                    "problems that are no longer visible because they were wiped."
                ),
                raw_evidence={"seconds_since_clear": time_since_clear}
            ))

    # === CHECK 2: Are readiness monitors complete? ===
    monitors = obd_data.get("monitors", {})
    if monitors:
        incomplete = [name for name, status in monitors.items()
                      if status in ("not_ready", "incomplete", False)]
        total = len(monitors)
        incomplete_count = len(incomplete)

        if incomplete_count > 0 and total > 0:
            ratio = incomplete_count / total
            if ratio > 0.4:
                signals.append(TruthSignal(
                    signal=DeceptionSignal.MONITORS_INCOMPLETE,
                    severity="high" if ratio > 0.6 else "medium",
                    human_explanation=(
                        f"{incomplete_count} out of {total} system checks have not completed. "
                        f"This usually means the battery was disconnected or codes were cleared recently. "
                        f"The vehicle has not driven enough for the computer to re-verify itself. "
                        f"Incomplete monitors: {', '.join(incomplete)}"
                    ),
                    raw_evidence={"incomplete": incomplete, "total": total}
                ))

    # === CHECK 3: Fuel trim anomaly ===
    fuel_trim_short = obd_data.get("fuel_trim_short")
    fuel_trim_long = obd_data.get("fuel_trim_long")

    if fuel_trim_long is not None:
        if abs(fuel_trim_long) > 15:
            direction = "rich" if fuel_trim_long < -15 else "lean"
            signals.append(TruthSignal(
                signal=DeceptionSignal.FUEL_TRIM_ANOMALY,
                severity="medium",
                human_explanation=(
                    f"The engine is running significantly {direction}. "
                    f"Long term fuel trim is at {fuel_trim_long}%. Normal is between -10% and +10%. "
                    f"This suggests an underlying issue (vacuum leak, injector problem, or sensor fault) "
                    f"even if no codes are currently stored."
                ),
                raw_evidence={
                    "fuel_trim_short": fuel_trim_short,
                    "fuel_trim_long": fuel_trim_long
                }
            ))

    # === CHECK 4: O2 sensor flat line ===
    o2_voltage = obd_data.get("o2_voltage")
    if o2_voltage is not None:
        # O2 sensors should swing between ~0.1V and ~0.9V
        # A flat reading near 0.45V or stuck high/low = dead sensor
        if isinstance(o2_voltage, (int, float)):
            if 0.40 <= o2_voltage <= 0.50:
                signals.append(TruthSignal(
                    signal=DeceptionSignal.O2_SENSOR_FLAT,
                    severity="medium",
                    human_explanation=(
                        f"O2 sensor is reading a flat {o2_voltage}V. A healthy O2 sensor "
                        f"should be constantly switching between 0.1V and 0.9V. A flat reading "
                        f"near 0.45V usually means the sensor is dead or not responding. "
                        f"This can hide emissions problems and cause poor fuel economy."
                    ),
                    raw_evidence={"o2_voltage": o2_voltage}
                ))

    # === CHECK 5: Pending codes with no stored codes ===
    dtcs = obd_data.get("dtcs", [])
    pending_dtcs = obd_data.get("pending_dtcs", [])

    if len(pending_dtcs) > 0 and len(dtcs) == 0:
        signals.append(TruthSignal(
            signal=DeceptionSignal.PENDING_CODES_WITH_NO_STORED,
            severity="medium",
            human_explanation=(
                f"There are {len(pending_dtcs)} pending fault codes but no confirmed codes. "
                f"This means the computer has detected a problem but has not confirmed it yet. "
                f"Pending codes: {', '.join(pending_dtcs)}. "
                f"If someone recently cleared codes, these pending codes may be the same "
                f"problems coming back."
            ),
            raw_evidence={"pending": pending_dtcs, "stored": dtcs}
        ))

    # === CHECK 6: Freeze frame exists but no codes ===
    freeze_frame = obd_data.get("freeze_frame")
    if freeze_frame is not None and len(dtcs) == 0:
        signals.append(TruthSignal(
            signal=DeceptionSignal.FREEZE_FRAME_PRESENT_NO_CODES,
            severity="high",
            human_explanation=(
                "The vehicle has freeze frame data (a snapshot taken when a fault occurred) "
                "but no active fault codes. This strongly suggests codes were cleared after "
                "a fault happened. The freeze frame is evidence that a problem existed."
            ),
            raw_evidence={"freeze_frame": freeze_frame}
        ))

    # === BUILD THE REPORT ===
    if len(signals) == 0:
        status = TruthStatus.CLEAN
        headline = "Vehicle data appears consistent"
        detail = (
            "No signs of cleared codes, hidden problems, or data inconsistencies detected. "
            "Readiness monitors are complete and sensor readings are within normal range."
        )
        confidence = 0.85
        recommendations = ["Continue normal maintenance schedule"]
    elif any(s.severity == "high" for s in signals):
        status = TruthStatus.INCONSISTENT
        high_signals = [s for s in signals if s.severity == "high"]
        headline = f"Warning: {len(signals)} inconsistencies detected"
        detail = high_signals[0].human_explanation
        confidence = 0.75
        recommendations = [
            "Do not trust this vehicle state at face value",
            "Request a full independent inspection before purchasing or authorizing repairs",
            "Ask the seller or mechanic to explain why codes were cleared",
        ]
    else:
        status = TruthStatus.UNCERTAIN
        headline = f"{len(signals)} minor concerns detected"
        detail = signals[0].human_explanation
        confidence = 0.60
        recommendations = [
            "Monitor these readings over the next few drives",
            "Consider a follow-up scan after 50 miles of driving",
        ]

    return TruthReport(
        status=status,
        signals=signals,
        headline=headline,
        detail=detail,
        confidence=confidence,
        scanned_at=datetime.utcnow().isoformat(),
        recommendations=recommendations,
    )


def truth_report_to_dict(report: TruthReport) -> Dict:
    """Convert a TruthReport to a JSON-serializable dictionary."""
    return {
        "truth_status": report.status.value,
        "headline": report.headline,
        "detail": report.detail,
        "confidence": report.confidence,
        "scanned_at": report.scanned_at,
        "signal_count": len(report.signals),
        "signals": [
            {
                "signal": s.signal.value,
                "severity": s.severity,
                "explanation": s.human_explanation,
            }
            for s in report.signals
        ],
        "recommendations": report.recommendations,
    }
