"""
Veracore — The Good Neighbor Guard
Built by Christopher Hughes · Sacramento, CA
Created with the help of AI collaborators (Claude · GPT · Gemini · Groq)
Truth · Safety · We Got Your Back

FAILURE PREDICTOR — Early Warning System
Catches problems before they become breakdowns.
"""

from dataclasses import dataclass
from typing import List, Dict, Optional, Any
from enum import Enum


class HealthStatus(Enum):
    STABLE = "stable"
    WARNING = "warning"
    CRITICAL = "critical"
    UNCERTAIN = "uncertain"


@dataclass
class HealthSignal:
    system: str                 # "battery", "cooling", "fuel_system"
    status: HealthStatus
    human_explanation: str
    urgency: str                # "monitor", "schedule_service", "stop_driving"
    estimated_timeline: Optional[str] = None  # "2-3 weeks", "immediate"


@dataclass
class HealthReport:
    overall_status: HealthStatus
    signals: List[HealthSignal]
    headline: str
    recommendations: List[str]


def analyze_health(obd_data: Dict[str, Any]) -> HealthReport:
    """
    Analyze OBD sensor data for early signs of component failure.

    Watches:
    1. Battery voltage — weak battery before it dies
    2. Coolant temperature — overheating trend
    3. Fuel trim drift — system compensating for a growing problem
    """
    signals = []

    # === BATTERY HEALTH ===
    battery_voltage = obd_data.get("battery_voltage")
    if battery_voltage is not None:
        if battery_voltage < 11.8:
            signals.append(HealthSignal(
                system="battery",
                status=HealthStatus.CRITICAL,
                human_explanation=(
                    f"Battery voltage is {battery_voltage}V. A healthy battery reads 12.4V to 12.8V "
                    f"with the engine off, and 13.5V to 14.5V while running. "
                    f"At {battery_voltage}V this battery may not start the vehicle next time."
                ),
                urgency="schedule_service",
                estimated_timeline="Days — could fail any morning"
            ))
        elif battery_voltage < 12.2:
            signals.append(HealthSignal(
                system="battery",
                status=HealthStatus.WARNING,
                human_explanation=(
                    f"Battery voltage is {battery_voltage}V. This is below ideal "
                    f"(12.4V-12.8V engine off). The battery is weakening and may fail "
                    f"within a few weeks, especially in cold weather."
                ),
                urgency="monitor",
                estimated_timeline="2-4 weeks"
            ))

    # === COOLANT TEMPERATURE ===
    coolant_temp = obd_data.get("coolant_temp")
    if coolant_temp is not None:
        if coolant_temp > 230:  # Fahrenheit
            signals.append(HealthSignal(
                system="cooling",
                status=HealthStatus.CRITICAL,
                human_explanation=(
                    f"Coolant temperature is {coolant_temp}F. Normal operating range is "
                    f"195F-220F. At {coolant_temp}F the engine is overheating. "
                    f"Continued driving risks severe engine damage."
                ),
                urgency="stop_driving",
                estimated_timeline="Immediate — pull over safely"
            ))
        elif coolant_temp > 220:
            signals.append(HealthSignal(
                system="cooling",
                status=HealthStatus.WARNING,
                human_explanation=(
                    f"Coolant temperature is {coolant_temp}F. This is at the upper edge "
                    f"of normal. Could indicate a cooling system issue developing "
                    f"(thermostat, water pump, or low coolant)."
                ),
                urgency="schedule_service",
                estimated_timeline="1-2 weeks"
            ))

    # === FUEL TRIM DRIFT ===
    fuel_trim_long = obd_data.get("fuel_trim_long")
    if fuel_trim_long is not None:
        if abs(fuel_trim_long) > 20:
            direction = "rich" if fuel_trim_long < 0 else "lean"
            signals.append(HealthSignal(
                system="fuel_system",
                status=HealthStatus.WARNING,
                human_explanation=(
                    f"Long term fuel trim is at {fuel_trim_long}%. The engine is running "
                    f"significantly {direction}. The computer is compensating hard for "
                    f"a problem that will likely trigger a check engine light soon. "
                    f"Common causes: vacuum leak, failing fuel injector, or bad sensor."
                ),
                urgency="schedule_service",
                estimated_timeline="1-3 weeks before code appears"
            ))

    # === BUILD REPORT ===
    if not signals:
        return HealthReport(
            overall_status=HealthStatus.STABLE,
            signals=[],
            headline="All monitored systems are within normal range",
            recommendations=["Continue normal maintenance schedule"]
        )

    worst = HealthStatus.STABLE
    for s in signals:
        if s.status == HealthStatus.CRITICAL:
            worst = HealthStatus.CRITICAL
            break
        elif s.status == HealthStatus.WARNING:
            worst = HealthStatus.WARNING

    return HealthReport(
        overall_status=worst,
        signals=signals,
        headline=f"{len(signals)} health concern{'s' if len(signals) > 1 else ''} detected",
        recommendations=[s.human_explanation for s in signals if s.urgency != "monitor"]
    )


def health_report_to_dict(report: HealthReport) -> Dict:
    return {
        "health_status": report.overall_status.value,
        "headline": report.headline,
        "signal_count": len(report.signals),
        "signals": [
            {
                "system": s.system,
                "status": s.status.value,
                "explanation": s.human_explanation,
                "urgency": s.urgency,
                "timeline": s.estimated_timeline,
            }
            for s in report.signals
        ],
        "recommendations": report.recommendations,
    }
