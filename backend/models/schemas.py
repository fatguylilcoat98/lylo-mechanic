"""
The Good Neighbor Guard — LYLO Mechanic
Christopher Hughes · Sacramento, CA
AI Collaborators: Claude · GPT · Gemini · Groq
Truth · Safety · We Got Your Back

All data schemas for LYLO Mechanic.
"""

from dataclasses import dataclass, field
from typing import Optional, List, Literal
from datetime import datetime


# ─── VEHICLE ──────────────────────────────────────────────────────────────────

@dataclass
class VehicleProfile:
    vin: Optional[str] = None
    year: Optional[int] = None
    make: Optional[str] = None
    model: Optional[str] = None
    trim: Optional[str] = None
    engine: Optional[str] = None       # e.g. "2.4L I4 GDI"
    engine_type: Optional[str] = None  # "GDI", "port_injection", "diesel"
    transmission: Optional[str] = None # "6AT", "CVT", "6MT"
    drive_type: Optional[str] = None   # "FWD", "RWD", "AWD", "4WD"
    odometer: Optional[int] = None
    is_hybrid: bool = False
    is_ev: bool = False
    supported_pids: List[str] = field(default_factory=list)
    enhanced_protocol: bool = False

    def display_name(self) -> str:
        parts = [str(self.year or ""), self.make or "", self.model or "", self.trim or ""]
        return " ".join(p for p in parts if p).strip() or "Unknown Vehicle"


# ─── OBD SESSION ──────────────────────────────────────────────────────────────

@dataclass
class RawDTC:
    code: str
    status: Literal["active", "pending", "history"]
    description: Optional[str] = None

@dataclass
class RawPIDValue:
    name: str
    pid_code: str
    raw_value: Optional[float]
    unit: str
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

@dataclass
class FreezeFrame:
    dtc_trigger: str
    rpm: Optional[float] = None
    speed: Optional[float] = None
    coolant_temp: Optional[float] = None
    load: Optional[float] = None
    fuel_trim_st: Optional[float] = None
    fuel_trim_lt: Optional[float] = None

@dataclass
class ReadinessMonitor:
    name: str
    status: Literal["complete", "incomplete", "not_applicable"]

@dataclass
class OBDSessionInput:
    adapter_id: str = "SIMULATED"
    protocol: str = "ISO 15765-4 CAN"
    connection_quality: Literal["stable", "unstable", "dropped"] = "stable"
    read_complete: bool = True
    vehicle_profile: Optional[VehicleProfile] = None
    raw_dtcs: List[RawDTC] = field(default_factory=list)
    raw_pids: List[RawPIDValue] = field(default_factory=list)
    freeze_frame: Optional[FreezeFrame] = None
    readiness_monitors: List[ReadinessMonitor] = field(default_factory=list)
    codes_cleared_before_scan: bool = False


# ─── NORMALIZED VEHICLE STATE ─────────────────────────────────────────────────

@dataclass
class NormalizedPID:
    name: str
    pid_code: str
    raw_value: Optional[float]
    interpreted_value: Optional[float]
    unit: str
    normal_range_low: Optional[float]
    normal_range_high: Optional[float]
    deviation: Optional[Literal["HIGH", "LOW", "NORMAL"]]
    is_implausible: bool = False
    is_missing: bool = False
    is_unsupported: bool = False
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

@dataclass
class NormalizedDTC:
    code: str
    status: Literal["active", "pending", "history"]
    category: Literal["SAE_standard", "manufacturer_specific", "unknown"]
    system: Literal["powertrain", "body", "chassis", "network", "unknown"]
    description: str
    is_safety_related: bool = False
    cascade_candidate: bool = False
    freeze_frame_attached: bool = False

@dataclass
class VehicleState:
    vehicle: VehicleProfile
    dtcs: List[NormalizedDTC]
    pids: List[NormalizedPID]
    freeze_frame: Optional[FreezeFrame]
    readiness_monitors: List[ReadinessMonitor]
    session_flags: List[str]
    connection_quality: str
    read_complete: bool


# ─── DATA CONFIDENCE ──────────────────────────────────────────────────────────

@dataclass
class DataConfidence:
    connection_valid: bool
    read_complete: bool
    pid_coverage: Literal["full", "partial", "limited"]
    symptom_alignment: Literal["consistent", "conflicting", "neutral", "no_symptoms"]
    codes_possibly_cleared: bool
    monitors_incomplete: bool
    unstable_session: bool
    manufacturer_specific_unknowns: bool
    overall: float  # 0.0 – 1.0
    limit_reason: Optional[str]
    blocked_outputs: List[str]

    def label(self) -> str:
        if self.overall >= 0.80:
            return "HIGH"
        elif self.overall >= 0.55:
            return "MODERATE"
        elif self.overall >= 0.35:
            return "LOW"
        return "VERY LOW"

    def percent(self) -> int:
        return int(self.overall * 100)


# ─── SYMPTOM INTAKE ───────────────────────────────────────────────────────────

@dataclass
class SymptomIntake:
    primary_category: str
    subcategories: List[str] = field(default_factory=list)
    when_it_happens: List[str] = field(default_factory=list)
    severity: Literal["minor", "noticeable", "significant", "severe"] = "noticeable"
    frequency: Literal["once", "occasional", "frequent", "constant"] = "occasional"
    getting_worse: bool = False
    recent_repairs: Optional[str] = None
    codes_recently_cleared: Optional[bool] = None
    free_text: Optional[str] = None


# ─── DIAGNOSIS ────────────────────────────────────────────────────────────────

@dataclass
class DiagnosisHypothesis:
    cause_rank: int
    cause_id: str
    cause_name: str
    cause_description: str
    confidence_score: int  # 0–100
    confidence_basis: Literal["OBD_confirmed", "symptom_correlated", "plausible", "low_confidence"]
    supporting_evidence: List[str]
    what_could_make_this_wrong: List[str]
    is_downstream: bool = False
    probable_root_cause_id: Optional[str] = None
    requires_physical_inspection: bool = True

    def confidence_label(self) -> str:
        if self.confidence_score >= 75:
            return "HIGH"
        elif self.confidence_score >= 50:
            return "MODERATE"
        elif self.confidence_score >= 30:
            return "LOW"
        return "SPECULATIVE"


# ─── SAFETY ───────────────────────────────────────────────────────────────────

SAFETY_LEVELS = [
    "SAFE_TO_DRIVE",
    "DRIVE_SHORT_DISTANCE_ONLY",
    "INSPECT_SOON",
    "DO_NOT_DRIVE",
    "TOW_RECOMMENDED",
    "EMERGENCY_STOP_IMMEDIATELY",
]

@dataclass
class SafetyClassification:
    level: str
    triggering_conditions: List[str]
    reasoning: str
    symptom_overrides_sensor: bool = False
    user_must_acknowledge: bool = False

    def severity_index(self) -> int:
        try:
            return SAFETY_LEVELS.index(self.level)
        except ValueError:
            return 0

    def is_drive_blocking(self) -> bool:
        return self.severity_index() >= SAFETY_LEVELS.index("DO_NOT_DRIVE")

    def color_class(self) -> str:
        mapping = {
            "SAFE_TO_DRIVE": "safe",
            "DRIVE_SHORT_DISTANCE_ONLY": "caution",
            "INSPECT_SOON": "warning",
            "DO_NOT_DRIVE": "danger",
            "TOW_RECOMMENDED": "danger",
            "EMERGENCY_STOP_IMMEDIATELY": "emergency",
        }
        return mapping.get(self.level, "unknown")

    def display_label(self) -> str:
        return self.level.replace("_", " ")


# ─── DIY GATE ─────────────────────────────────────────────────────────────────

@dataclass
class DIYEligibility:
    verdict: Literal[
        "DIY_ALLOWED",
        "DIY_WITH_CAUTION",
        "ASSISTED_REPAIR_ONLY",
        "PROFESSIONAL_ONLY",
        "DANGEROUS_TO_ATTEMPT",
    ]
    skill_level_required: Literal["beginner", "intermediate", "advanced", "professional"]
    risk_level: Literal["low", "medium", "high", "critical"]
    hard_stop: bool
    hard_stop_reason: Optional[str]
    required_tools: List[str]
    special_equipment: List[str]
    failure_mode_catastrophic: bool
    requires_recalibration: bool
    requires_programming: bool

    def is_blocked(self) -> bool:
        return self.hard_stop or self.verdict == "DANGEROUS_TO_ATTEMPT"

    def display_label(self) -> str:
        return self.verdict.replace("_", " ")


# ─── COST ─────────────────────────────────────────────────────────────────────

@dataclass
class PartItem:
    part_name: str
    oem_part_number: Optional[str]
    aftermarket_note: Optional[str]
    qty: int
    cost_low: int
    cost_high: int

@dataclass
class CostTier:
    label: str
    total_low: int
    total_high: int
    parts_low: int = 0
    parts_high: int = 0
    labor_low: int = 0
    labor_high: int = 0
    note: Optional[str] = None

@dataclass
class RepairCostEstimate:
    cause_id: str
    volatility: Literal["LOW", "MEDIUM", "HIGH"]
    pricing_data_date: str
    stale_warning: bool
    diy: CostTier
    shop: CostTier
    dealership: CostTier
    parts_list: List[PartItem]
    labor_hours_low: float
    labor_hours_high: float
    time_to_complete_diy: str
    uncertainty_factors: List[str]
    what_could_make_estimate_wrong: List[str]


# ─── TUTORIAL ─────────────────────────────────────────────────────────────────

@dataclass
class TutorialStep:
    step_number: int
    title: str
    instruction: str
    torque_spec: Optional[str] = None
    warning: Optional[str] = None
    done_wrong_looks_like: Optional[str] = None

@dataclass
class Tutorial:
    cause_id: str
    repair_name: str
    why_suggested: str
    safety_precautions: List[str]
    tools_required: List[str]
    parts_required: List[PartItem]
    point_of_no_return: Optional[str]
    steps: List[TutorialStep]
    verification_steps: List[str]
    if_not_fixed: str


# ─── VERACORE FLAGS ───────────────────────────────────────────────────────────

@dataclass
class VeracoreFlag:
    flag_type: Literal["weak_evidence", "conflicting_data", "stale_pricing", "safety_concern", "overconfident"]
    target: str  # which part of the response this challenges
    message: str
    severity: Literal["info", "caution", "critical"]


# ─── FINAL RESPONSE ───────────────────────────────────────────────────────────

@dataclass
class MechanicResponse:
    session_id: str
    vehicle: VehicleProfile
    confidence: DataConfidence
    safety: SafetyClassification
    hypotheses: List[DiagnosisHypothesis]
    diy_eligibility: Optional[DIYEligibility]
    cost_estimates: List[RepairCostEstimate]
    tutorial_available: bool
    tutorial_blocked_reason: Optional[str]
    veracore_flags: List[VeracoreFlag]
    handshake_required: bool
    handshake_reason: Optional[str]
    what_we_know: List[str]
    what_this_might_mean: str
    what_to_check_first: List[str]
    professional_help_triggers: List[str]
    session_flags: List[str]
    handshake_api: Optional[dict] = None

    def to_dict(self) -> dict:
        import dataclasses
        return dataclasses.asdict(self)
