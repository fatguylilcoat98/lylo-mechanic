"""
The Good Neighbor Guard — LYLO Mechanic
Christopher Hughes · Sacramento, CA
AI Collaborators: Claude · GPT · Gemini · Groq
Truth · Safety · We Got Your Back

Normalization layer: converts raw OBD data into structured VehicleState.
"""

import json
import os
from typing import List, Optional
from models.schemas import (
    OBDSessionInput, VehicleState, NormalizedDTC, NormalizedPID,
    RawDTC, RawPIDValue, VehicleProfile
)

# Load DTC database once at import
_DTC_DB_PATH = os.path.join(os.path.dirname(__file__), "../data/dtc_db/dtc_codes.json")
_DTC_DB: dict = {}

def _load_dtc_db():
    global _DTC_DB
    if not _DTC_DB:
        try:
            with open(_DTC_DB_PATH) as f:
                _DTC_DB = json.load(f)
        except Exception:
            _DTC_DB = {}

# PID normal ranges (unit, low, high)
PID_RANGES = {
    "ENGINE_COOLANT_TEMP":       ("°F", 160, 225),
    "ENGINE_RPM":                ("rpm", 600, 900),   # idle range
    "VEHICLE_SPEED":             ("mph", None, None),
    "SHORT_TERM_FUEL_TRIM_B1":   ("%",  -10, 10),
    "LONG_TERM_FUEL_TRIM_B1":    ("%",  -10, 10),
    "SHORT_TERM_FUEL_TRIM_B2":   ("%",  -10, 10),
    "LONG_TERM_FUEL_TRIM_B2":    ("%",  -10, 10),
    "MAF_AIR_FLOW_RATE":         ("g/s", 2, 15),      # idle range
    "THROTTLE_POSITION":         ("%",   0, 100),
    "INTAKE_AIR_TEMP":           ("°F",  32, 120),
    "BATTERY_VOLTAGE":           ("V",   13.5, 14.8),
    "ENGINE_LOAD":               ("%",   0, 100),
    "O2_SENSOR_B1S1":            ("V",   0.1, 0.9),
    "O2_SENSOR_B1S2":            ("V",   0.1, 0.9),
}

# Implausible value guards (absolute physical limits)
PID_IMPLAUSIBLE = {
    "ENGINE_COOLANT_TEMP":  (-40, 300),
    "ENGINE_RPM":           (0, 9000),
    "BATTERY_VOLTAGE":      (0, 18),
    "MAF_AIR_FLOW_RATE":    (0, 500),
    "THROTTLE_POSITION":    (0, 100),
}


def normalize_session(session: OBDSessionInput) -> VehicleState:
    """Main entry point: normalize a raw OBD session into VehicleState."""
    _load_dtc_db()

    session_flags = _detect_session_flags(session)
    dtcs = [_normalize_dtc(d, session.vehicle_profile) for d in session.raw_dtcs]
    pids = [_normalize_pid(p) for p in session.raw_pids]
    dtcs = _detect_cascades(dtcs)

    return VehicleState(
        vehicle=session.vehicle_profile or VehicleProfile(),
        dtcs=dtcs,
        pids=pids,
        freeze_frame=session.freeze_frame,
        readiness_monitors=session.readiness_monitors,
        session_flags=session_flags,
        connection_quality=session.connection_quality,
        read_complete=session.read_complete,
    )


def _normalize_dtc(raw: RawDTC, vehicle: Optional[VehicleProfile]) -> NormalizedDTC:
    code = raw.code.upper().strip()
    db_entry = _DTC_DB.get(code, {})

    # Determine category
    if code in _DTC_DB:
        category = db_entry.get("category", "SAE_standard")
        description = db_entry.get("description", raw.description or "No description available")
        system = db_entry.get("system", "unknown")
        safety_related = db_entry.get("safety_related", False)
    elif _is_manufacturer_specific(code):
        category = "manufacturer_specific"
        description = f"Manufacturer-specific code — interpretation requires {vehicle.make if vehicle and vehicle.make else 'make/model'} service data"
        system = _infer_system_from_code(code)
        safety_related = _is_potentially_safety_related(code)
    else:
        category = "unknown"
        description = "Unknown code — cannot interpret without service data"
        system = "unknown"
        safety_related = False

    return NormalizedDTC(
        code=code,
        status=raw.status,
        category=category,
        system=system,
        description=description,
        is_safety_related=safety_related,
        cascade_candidate=False,  # updated by _detect_cascades
        freeze_frame_attached=False,
    )


def _normalize_pid(raw: RawPIDValue) -> NormalizedPID:
    name = raw.name.upper().replace(" ", "_")
    range_info = PID_RANGES.get(name)
    implausible_range = PID_IMPLAUSIBLE.get(name)

    unit = range_info[0] if range_info else raw.unit
    low = range_info[1] if range_info else None
    high = range_info[2] if range_info else None

    is_missing = raw.raw_value is None
    is_implausible = False
    deviation = None

    if not is_missing and raw.raw_value is not None:
        # Check implausible
        if implausible_range:
            if raw.raw_value < implausible_range[0] or raw.raw_value > implausible_range[1]:
                is_implausible = True

        # Deviation from normal
        if not is_implausible and low is not None and high is not None:
            if raw.raw_value < low:
                deviation = "LOW"
            elif raw.raw_value > high:
                deviation = "HIGH"
            else:
                deviation = "NORMAL"

    return NormalizedPID(
        name=name,
        pid_code=raw.pid_code,
        raw_value=raw.raw_value,
        interpreted_value=raw.raw_value if not is_implausible else None,
        unit=unit,
        normal_range_low=low,
        normal_range_high=high,
        deviation=deviation,
        is_implausible=is_implausible,
        is_missing=is_missing,
        is_unsupported=False,
        timestamp=raw.timestamp,
    )


def _detect_cascades(dtcs: List[NormalizedDTC]) -> List[NormalizedDTC]:
    """Flag codes that are likely downstream of other codes present."""
    codes_present = {d.code for d in dtcs}

    # If P0562 (low voltage) is present, most other codes become cascade candidates
    voltage_cascade = "P0562" in codes_present

    # Misfire can cascade to P0420
    misfire_present = any(c.startswith("P030") for c in codes_present)

    for dtc in dtcs:
        if voltage_cascade and dtc.code != "P0562":
            if dtc.system in ("network", "body") or dtc.code.startswith("U"):
                dtc.cascade_candidate = True
        if misfire_present and dtc.code == "P0420":
            dtc.cascade_candidate = True

    return dtcs


def _detect_session_flags(session: OBDSessionInput) -> List[str]:
    flags = []
    if session.codes_cleared_before_scan:
        flags.append("CODES_POSSIBLY_CLEARED")
    if not session.read_complete:
        flags.append("INCOMPLETE_READ")
    if session.connection_quality in ("unstable", "dropped"):
        flags.append("UNSTABLE_CONNECTION")
    if session.readiness_monitors:
        incomplete = [m for m in session.readiness_monitors if m.status == "incomplete"]
        if incomplete:
            flags.append("MONITORS_INCOMPLETE")
    if session.vehicle_profile and (session.vehicle_profile.is_hybrid or session.vehicle_profile.is_ev):
        flags.append("HIGH_VOLTAGE_VEHICLE")
    return flags


def _is_manufacturer_specific(code: str) -> bool:
    if len(code) < 2:
        return False
    if code[0] == "P":
        try:
            second_digit = int(code[1])
            return second_digit in (1, 3)
        except (ValueError, IndexError):
            return False
    return code[0] in ("B", "C", "U") and code not in _DTC_DB


def _infer_system_from_code(code: str) -> str:
    prefix = code[0].upper()
    return {"P": "powertrain", "B": "body", "C": "chassis", "U": "network"}.get(prefix, "unknown")


def _is_potentially_safety_related(code: str) -> bool:
    prefix = code[0].upper()
    return prefix in ("B", "C")  # Body/chassis manufacturer codes are potentially safety-related


def get_pid_value(state: VehicleState, name: str) -> Optional[float]:
    """Helper to extract a PID value by name from VehicleState."""
    name = name.upper().replace(" ", "_")
    for pid in state.pids:
        if pid.name == name and not pid.is_missing and not pid.is_implausible:
            return pid.interpreted_value
    return None


def get_pid(state: VehicleState, name: str) -> Optional[NormalizedPID]:
    """Helper to get the full NormalizedPID object."""
    name = name.upper().replace(" ", "_")
    for pid in state.pids:
        if pid.name == name:
            return pid
    return None
