"""
The Good Neighbor Guard — LYLO Mechanic
Christopher Hughes · Sacramento, CA
AI Collaborators: Claude · GPT · Gemini · Groq
Truth · Safety · We Got Your Back

DIY eligibility gate. Hard blocks are non-overridable.
"""

from models.schemas import DIYEligibility, SafetyClassification, VehicleProfile

# ── HARD BLOCK CATEGORIES ────────────────────────────────────────────────────
# These can NEVER be DIY regardless of skill level.

HARD_BLOCK_REPAIRS = {
    "airbag_module", "clock_spring", "srs_harness",
    "abs_module", "abs_hydraulic_unit",
    "master_cylinder", "brake_lines", "brake_proportioning_valve",
    "high_voltage_battery", "hv_inverter", "hv_harness",
    "timing_belt_interference", "timing_chain_interference",
    "fuel_injector_hpfp", "high_pressure_fuel_pump",
    "transmission_internal", "transfer_case_internal",
    "steering_rack", "steering_column",
    "throttle_body_electronic_requiring_reprogram",
}

HARD_BLOCK_REASON = {
    "airbag_module": "SRS/airbag components require professional handling — accidental deployment is life-threatening",
    "clock_spring": "SRS system — accidental deployment risk",
    "abs_module": "ABS module replacement requires professional bleeding and often module programming",
    "abs_hydraulic_unit": "ABS hydraulic unit requires professional pressure bleeding",
    "master_cylinder": "Brake hydraulic work requires professional pressure testing and bleeding",
    "brake_lines": "Brake hydraulic work — professional only",
    "high_voltage_battery": "High-voltage battery on hybrid/EV — requires specialized equipment and training",
    "hv_inverter": "High-voltage component — trained technician required",
    "timing_belt_interference": "Incorrect timing on interference engine causes catastrophic engine damage",
    "timing_chain_interference": "Incorrect timing on interference engine causes catastrophic engine damage",
    "fuel_injector_hpfp": "High-pressure fuel system — fuel under extreme pressure, fire risk",
    "transmission_internal": "Internal transmission work requires specialized tools and expertise",
    "steering_rack": "Steering rack replacement requires alignment and may require programming",
}

# ── REPAIR PROFILES ──────────────────────────────────────────────────────────
# skill: beginner / intermediate / advanced / professional
# risk: low / medium / high / critical
# tools: list of tools required
# recalibration: whether post-repair recalibration is needed

REPAIR_PROFILES = {
    "spark_plug_cyl1": {
        "skill": "beginner",
        "risk": "low",
        "tools": ["Ratchet set", "Spark plug socket", "Torque wrench", "Extension bar"],
        "special_equipment": [],
        "catastrophic_failure_mode": False,
        "recalibration": False,
        "programming": False,
        "caution_step": "Do not overtorque plugs — follow exact torque spec to avoid cracking porcelain in bore",
    },
    "ignition_coil_cyl1": {
        "skill": "beginner",
        "risk": "low",
        "tools": ["7mm or 10mm socket", "Ratchet", "Extension"],
        "special_equipment": [],
        "catastrophic_failure_mode": False,
        "recalibration": False,
        "programming": False,
        "caution_step": None,
    },
    "vacuum_leak": {
        "skill": "intermediate",
        "risk": "low",
        "tools": ["Smoke machine (rental) OR carb cleaner spray", "Flashlight", "Inspection mirror"],
        "special_equipment": ["Smoke machine (strongly recommended)"],
        "catastrophic_failure_mode": False,
        "recalibration": False,
        "programming": False,
        "caution_step": "Do not use open flame to find vacuum leaks — use carb cleaner SPRAY only, away from hot surfaces",
    },
    "exhaust_manifold_leak": {
        "skill": "intermediate",
        "risk": "medium",
        "tools": ["Socket set", "Torque wrench", "Penetrating oil", "Stud extractor (may need)", "Gasket scraper"],
        "special_equipment": ["Vehicle lift or sturdy ramps"],
        "catastrophic_failure_mode": False,
        "recalibration": False,
        "programming": False,
        "caution_step": "Seized exhaust manifold studs often break during removal — budget for stud extraction if vehicle is older",
    },
    "catalytic_converter_failure": {
        "skill": "intermediate",
        "risk": "medium",
        "tools": ["Breaker bar", "Penetrating oil", "O2 sensor socket", "Vehicle lift or ramps"],
        "special_equipment": ["Vehicle lift"],
        "catastrophic_failure_mode": False,
        "recalibration": False,
        "programming": False,
        "caution_step": "Rule out upstream exhaust leaks and O2 sensors before replacing — P0420 is most commonly misdiagnosed",
    },
    "faulty_downstream_o2": {
        "skill": "beginner",
        "risk": "low",
        "tools": ["O2 sensor socket", "Ratchet", "Penetrating oil", "Torque wrench"],
        "special_equipment": [],
        "catastrophic_failure_mode": False,
        "recalibration": False,
        "programming": False,
        "caution_step": "Apply anti-seize to threads; torque to spec — overtorquing cracks the housing",
    },
    "wrong_oil_viscosity": {
        "skill": "beginner",
        "risk": "low",
        "tools": ["Oil drain pan", "Oil drain plug socket", "Oil filter wrench"],
        "special_equipment": [],
        "catastrophic_failure_mode": False,
        "recalibration": False,
        "programming": False,
        "caution_step": None,
    },
    "vvt_solenoid": {
        "skill": "intermediate",
        "risk": "medium",
        "tools": ["Socket set", "Torque wrench", "Rags"],
        "special_equipment": [],
        "catastrophic_failure_mode": False,
        "recalibration": False,
        "programming": False,
        "caution_step": "Use correct torque spec — VVT solenoids can crack if overtorqued",
    },
    "weak_battery": {
        "skill": "beginner",
        "risk": "low",
        "tools": ["10mm wrench or socket", "Battery terminal brush"],
        "special_equipment": [],
        "catastrophic_failure_mode": False,
        "recalibration": False,
        "programming": False,
        "caution_step": "Some vehicles (BMW, Mercedes, VW) require battery registration after replacement — check your specific model",
    },
    "tire_balance": {
        "skill": "professional",
        "risk": "low",
        "tools": [],
        "special_equipment": ["Wheel balancing machine — shop only"],
        "catastrophic_failure_mode": False,
        "recalibration": False,
        "programming": False,
        "caution_step": None,
    },
    "wheel_bearing": {
        "skill": "advanced",
        "risk": "high",
        "tools": ["Socket set", "Torque wrench", "Breaker bar", "Axle nut socket"],
        "special_equipment": ["Hydraulic press (for pressed bearings)", "Hub puller"],
        "catastrophic_failure_mode": True,
        "recalibration": False,
        "programming": False,
        "caution_step": "Wheel bearing failure can cause wheel separation at speed — do not delay repair",
    },
    "timing_chain_stretch": {
        "skill": "professional",
        "risk": "critical",
        "tools": [],
        "special_equipment": ["Professional only — specialized tooling required"],
        "catastrophic_failure_mode": True,
        "recalibration": False,
        "programming": False,
        "caution_step": None,
    },
    "upstream_o2_issue": {
        "skill": "beginner",
        "risk": "low",
        "tools": ["O2 sensor socket", "Ratchet", "Penetrating oil"],
        "special_equipment": [],
        "catastrophic_failure_mode": False,
        "recalibration": False,
        "programming": False,
        "caution_step": "Apply anti-seize to threads; do not damage wiring harness connector",
    },
    "cv_axle": {
        "skill": "advanced",
        "risk": "high",
        "tools": ["Socket set", "Breaker bar", "Axle nut socket", "Pry bar", "Mallet"],
        "special_equipment": ["Vehicle lift or jack stands"],
        "catastrophic_failure_mode": True,
        "recalibration": False,
        "programming": False,
        "caution_step": "CV axle failure at speed causes loss of drive — do not drive with a clicking CV joint",
    },
    "fuel_injector_cyl1": {
        "skill": "intermediate",
        "risk": "medium",
        "tools": ["Socket set", "Fuel line disconnect tool", "Torque wrench"],
        "special_equipment": [],
        "catastrophic_failure_mode": False,
        "recalibration": False,
        "programming": False,
        "caution_step": "Relieve fuel pressure before disconnecting — fire risk from pressurized fuel",
    },
    "weak_fuel_pump": {
        "skill": "advanced",
        "risk": "high",
        "tools": ["Socket set", "Fuel line disconnect tools", "Multimeter"],
        "special_equipment": ["Fuel pressure gauge"],
        "catastrophic_failure_mode": False,
        "recalibration": False,
        "programming": False,
        "caution_step": "Work in well-ventilated area — fuel vapors are extremely flammable. Disconnect battery first.",
    },
    "dirty_maf_sensor": {
        "skill": "beginner",
        "risk": "low",
        "tools": ["Screwdriver or Torx bit", "MAF sensor cleaner spray"],
        "special_equipment": [],
        "catastrophic_failure_mode": False,
        "recalibration": False,
        "programming": False,
        "caution_step": "Use only MAF-specific cleaner — brake cleaner or carb cleaner will destroy the sensor element",
    },
    "brake_fluid_issue": {
        "skill": "intermediate",
        "risk": "high",
        "tools": ["Wrench set", "Brake bleeder kit", "Turkey baster (for old fluid removal)"],
        "special_equipment": ["Brake bleeding kit or assistant"],
        "catastrophic_failure_mode": True,
        "recalibration": False,
        "programming": False,
        "caution_step": "Air in brake lines causes brake failure — bleed all four corners in correct order. Test brakes at low speed before driving.",
    },
    "brake_pad_wear": {
        "skill": "intermediate",
        "risk": "medium",
        "tools": ["Socket set", "C-clamp or brake piston tool", "Wire brush", "Torque wrench"],
        "special_equipment": ["Jack stands"],
        "catastrophic_failure_mode": False,
        "recalibration": False,
        "programming": False,
        "caution_step": "Compress piston slowly — never pry against rotor face. Check rotor thickness before reinstalling.",
    },
    "failing_alternator": {
        "skill": "intermediate",
        "risk": "medium",
        "tools": ["Socket set", "Wrench set", "Belt tensioner tool", "Multimeter"],
        "special_equipment": [],
        "catastrophic_failure_mode": False,
        "recalibration": False,
        "programming": False,
        "caution_step": "Disconnect battery before removal. Some vehicles require belt routing diagram — photograph before disassembly.",
    },
}


def evaluate_diy_eligibility(
    cause_id: str,
    vehicle: VehicleProfile,
    safety: SafetyClassification,
) -> DIYEligibility:
    """
    Determine DIY eligibility for a given repair cause.
    Safety gate runs first — if vehicle is unsafe to operate, no DIY.
    """

    # Safety gate — never allow DIY on immobilized vehicles
    if safety.is_drive_blocking():
        return DIYEligibility(
            verdict="DANGEROUS_TO_ATTEMPT",
            skill_level_required="professional",
            risk_level="critical",
            hard_stop=True,
            hard_stop_reason="Vehicle is classified as DO NOT DRIVE or worse. Assess and repair with vehicle secured and not operating.",
            required_tools=[],
            special_equipment=[],
            failure_mode_catastrophic=True,
            requires_recalibration=False,
            requires_programming=False,
        )

    # Hard block check
    if cause_id in HARD_BLOCK_REPAIRS:
        return DIYEligibility(
            verdict="DANGEROUS_TO_ATTEMPT",
            skill_level_required="professional",
            risk_level="critical",
            hard_stop=True,
            hard_stop_reason=HARD_BLOCK_REASON.get(cause_id, "This repair category requires professional handling."),
            required_tools=[],
            special_equipment=[],
            failure_mode_catastrophic=True,
            requires_recalibration=True,
            requires_programming=False,
        )

    # Hybrid/EV check
    if (vehicle.is_hybrid or vehicle.is_ev) and "high_voltage" in cause_id.lower():
        return DIYEligibility(
            verdict="DANGEROUS_TO_ATTEMPT",
            skill_level_required="professional",
            risk_level="critical",
            hard_stop=True,
            hard_stop_reason="High-voltage hybrid/EV system — requires certified technician with HV safety training",
            required_tools=[],
            special_equipment=["HV safety equipment", "Certified technician"],
            failure_mode_catastrophic=True,
            requires_recalibration=True,
            requires_programming=False,
        )

    # Look up repair profile
    profile = REPAIR_PROFILES.get(cause_id)
    if not profile:
        return DIYEligibility(
            verdict="PROFESSIONAL_ONLY",
            skill_level_required="professional",
            risk_level="medium",
            hard_stop=False,
            hard_stop_reason="No DIY profile available for this repair type — professional assessment recommended",
            required_tools=[],
            special_equipment=[],
            failure_mode_catastrophic=False,
            requires_recalibration=False,
            requires_programming=False,
        )

    skill = profile["skill"]
    risk = profile["risk"]

    # Professional-only repairs
    if skill == "professional":
        return DIYEligibility(
            verdict="PROFESSIONAL_ONLY",
            skill_level_required="professional",
            risk_level=risk,
            hard_stop=False,
            hard_stop_reason="This repair requires professional tools or equipment not available to most DIYers",
            required_tools=profile["tools"],
            special_equipment=profile["special_equipment"],
            failure_mode_catastrophic=profile["catastrophic_failure_mode"],
            requires_recalibration=profile["recalibration"],
            requires_programming=profile["programming"],
        )

    # Catastrophic failure mode + advanced skill = assisted only
    if profile["catastrophic_failure_mode"] and skill in ("intermediate", "advanced"):
        return DIYEligibility(
            verdict="ASSISTED_REPAIR_ONLY",
            skill_level_required=skill,
            risk_level=risk,
            hard_stop=False,
            hard_stop_reason=None,
            required_tools=profile["tools"],
            special_equipment=profile["special_equipment"],
            failure_mode_catastrophic=True,
            requires_recalibration=profile["recalibration"],
            requires_programming=profile["programming"],
        )

    # Caution step present = DIY with caution
    if profile.get("caution_step"):
        return DIYEligibility(
            verdict="DIY_WITH_CAUTION",
            skill_level_required=skill,
            risk_level=risk,
            hard_stop=False,
            hard_stop_reason=None,
            required_tools=profile["tools"],
            special_equipment=profile["special_equipment"],
            failure_mode_catastrophic=profile["catastrophic_failure_mode"],
            requires_recalibration=profile["recalibration"],
            requires_programming=profile["programming"],
        )

    return DIYEligibility(
        verdict="DIY_ALLOWED",
        skill_level_required=skill,
        risk_level=risk,
        hard_stop=False,
        hard_stop_reason=None,
        required_tools=profile["tools"],
        special_equipment=profile["special_equipment"],
        failure_mode_catastrophic=profile["catastrophic_failure_mode"],
        requires_recalibration=profile["recalibration"],
        requires_programming=profile["programming"],
    )
