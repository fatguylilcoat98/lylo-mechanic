"""
Veracore — The Good Neighbor Guard
Built by Christopher Hughes · Sacramento, CA
Created with the help of AI collaborators (Claude · GPT · Gemini · Groq)
Truth · Safety · We Got Your Back

QUOTE AUDITOR — Mechanic Claim Verification

The fourth layer of the truth system, and the one that closes the loop.

  TRUTH DETECTOR     catches HIDDEN problems    (problems someone erased)
  FAILURE PREDICTOR  catches COMING problems    (problems before they hit)
  EVENT BLACK BOX    catches PAST problems      (events that actually happened)
  QUOTE AUDITOR      catches INVENTED problems  (repairs you don't actually need)

This is the bridge from CLASPION's doctrine — "refuse to trust a claim when
the evidence is dressed up as confidence" — into the exact place real people
get hurt every single day: the repair shop.

A mechanic tells you "you need a new catalytic converter, $1,800."
You type that into LYLO. LYLO looks at your OBD data and says either:
  - "The data supports this. Here is what matches."
  - "The data does NOT support this. Here is what's missing. Push back."

The ShopScript returned is what the user says at the counter. Plain English.
Non-confrontational. Evidence-based. Harder to brush off than a vague
'let me get a second opinion.'
"""

import re
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any, Tuple
from enum import Enum
from datetime import datetime


class AuditVerdict(Enum):
    SUPPORTED = "supported"                     # Evidence matches the quote
    NOT_SUPPORTED = "not_supported"             # Evidence contradicts or is absent
    PARTIALLY_SUPPORTED = "partially_supported" # Some evidence, not conclusive
    INSUFFICIENT_DATA = "insufficient_data"     # Can't audit — need more scan data
    UNKNOWN_REPAIR = "unknown_repair"           # Don't recognize this repair type


@dataclass
class RepairProfile:
    """A known repair and the OBD evidence that would legitimately support it."""
    repair_id: str
    display_name: str
    # DTC families that support this repair (regex fragments)
    supporting_dtc_patterns: List[str]
    # Sensor conditions (described in plain English, shown to user)
    supporting_sensor_conditions: List[str]
    # Function that checks OBD data for the sensor conditions
    sensor_check: Optional[Any] = None  # Callable[[dict], bool]
    # Typical cost range (for sanity checking quoted prices)
    typical_cost_low: Optional[int] = None
    typical_cost_high: Optional[int] = None
    # Known ways to misdiagnose this
    common_misdiagnoses: List[str] = field(default_factory=list)


@dataclass
class AuditResult:
    verdict: AuditVerdict
    repair_id: Optional[str]
    repair_name: Optional[str]
    headline: str
    detail: str
    matching_evidence: List[str]    # Things in the data that DO support this
    missing_evidence: List[str]     # Things that SHOULD be there but aren't
    quoted_price: Optional[int]
    price_verdict: Optional[str]    # "reasonable", "high", "very_high", "low"
    typical_range: Optional[str]
    shop_script: str                # Plain-English script for the user
    confidence: float
    audited_at: str


# ══════════════════════════════════════════════════════════════════════════
# REPAIR CATALOG
# ══════════════════════════════════════════════════════════════════════════
# Each repair lists the OBD evidence that would ACTUALLY support it.
# If someone tries to sell you the repair and NONE of this evidence exists,
# the data does not support the diagnosis. That's the honest answer.

def _has_fuel_trim_anomaly(data: Dict) -> bool:
    ft = data.get("fuel_trim_long")
    return ft is not None and abs(ft) > 15


def _has_flat_o2(data: Dict) -> bool:
    v = data.get("o2_voltage")
    return v is not None and isinstance(v, (int, float)) and 0.40 <= v <= 0.50


def _has_low_battery(data: Dict) -> bool:
    v = data.get("battery_voltage")
    return v is not None and v < 12.2


def _has_low_charging(data: Dict) -> bool:
    # Alternator evidence: voltage < 13.5 while engine running
    v = data.get("battery_voltage")
    rpm = data.get("rpm") or 0
    return v is not None and rpm > 0 and v < 13.5


def _has_high_coolant(data: Dict) -> bool:
    t = data.get("coolant_temp")
    return t is not None and t > 220


REPAIR_CATALOG: Dict[str, RepairProfile] = {
    "catalytic_converter": RepairProfile(
        repair_id="catalytic_converter",
        display_name="Catalytic converter replacement",
        supporting_dtc_patterns=[r"^P042[0-9]$", r"^P043[0-9]$"],
        supporting_sensor_conditions=[
            "P0420 or P0430 fault code (catalyst efficiency below threshold)",
            "O2 sensor readings consistent with a failing catalyst",
        ],
        sensor_check=None,
        typical_cost_low=400,
        typical_cost_high=2200,
        common_misdiagnoses=[
            "P0420 is the most misdiagnosed code — it is often actually "
            "an O2 sensor, an exhaust leak, or broken studs, not the cat.",
            "A shop that recommends cat replacement without testing the "
            "O2 sensors first is skipping the cheap fix.",
        ],
    ),
    "oxygen_sensor": RepairProfile(
        repair_id="oxygen_sensor",
        display_name="Oxygen (O2) sensor replacement",
        supporting_dtc_patterns=[r"^P013[0-9]$", r"^P014[0-9]$", r"^P015[0-9]$", r"^P016[0-9]$"],
        supporting_sensor_conditions=[
            "P013X / P014X / P015X / P016X fault code",
            "Flat O2 sensor voltage (stuck near 0.45V)",
        ],
        sensor_check=_has_flat_o2,
        typical_cost_low=150,
        typical_cost_high=500,
        common_misdiagnoses=[
            "Running rich / running lean does not automatically mean the "
            "O2 sensor is bad. Check for vacuum leaks and fuel system "
            "issues first.",
        ],
    ),
    "spark_plugs": RepairProfile(
        repair_id="spark_plugs",
        display_name="Spark plug replacement",
        supporting_dtc_patterns=[r"^P030[0-9]$"],
        supporting_sensor_conditions=[
            "Misfire codes (P0300-P0308)",
            "Long-term fuel trim anomaly",
        ],
        sensor_check=None,
        typical_cost_low=80,
        typical_cost_high=450,
        common_misdiagnoses=[
            "Misfires can be caused by coils, injectors, vacuum leaks, "
            "or low compression — not just plugs.",
        ],
    ),
    "ignition_coil": RepairProfile(
        repair_id="ignition_coil",
        display_name="Ignition coil replacement",
        supporting_dtc_patterns=[r"^P035[1-6]$", r"^P030[1-8]$"],
        supporting_sensor_conditions=[
            "Specific cylinder misfire code (e.g., P0301 for cylinder 1)",
            "P0351-P0356 coil-specific fault codes",
        ],
        sensor_check=None,
        typical_cost_low=80,
        typical_cost_high=300,
        common_misdiagnoses=[
            "Replacing ALL coils because one is bad is a common upsell. "
            "Ask which cylinder is misfiring and replace only that coil.",
        ],
    ),
    "battery": RepairProfile(
        repair_id="battery",
        display_name="Battery replacement",
        supporting_dtc_patterns=[r"^P0562$", r"^P0563$"],
        supporting_sensor_conditions=[
            "Battery voltage below 12.2V (engine off)",
            "P0562 or P0563 fault code",
        ],
        sensor_check=_has_low_battery,
        typical_cost_low=120,
        typical_cost_high=350,
        common_misdiagnoses=[
            "A weak battery can also be caused by a bad alternator — make "
            "sure the alternator is tested before replacing the battery.",
            "Parasitic drains (something draining the battery while parked) "
            "should be ruled out.",
        ],
    ),
    "alternator": RepairProfile(
        repair_id="alternator",
        display_name="Alternator replacement",
        supporting_dtc_patterns=[r"^P0620$", r"^P0621$", r"^P0622$"],
        supporting_sensor_conditions=[
            "Charging voltage below 13.5V with engine running",
            "P0620-P0622 charging system fault code",
        ],
        sensor_check=_has_low_charging,
        typical_cost_low=300,
        typical_cost_high=900,
        common_misdiagnoses=[
            "A bad battery can mimic alternator symptoms. Both should be "
            "load-tested separately before replacing either.",
        ],
    ),
    "mass_airflow_sensor": RepairProfile(
        repair_id="mass_airflow_sensor",
        display_name="Mass airflow (MAF) sensor replacement",
        supporting_dtc_patterns=[r"^P010[0-4]$"],
        supporting_sensor_conditions=[
            "P0100-P0104 MAF sensor fault codes",
            "Fuel trim anomaly consistent with airflow reading issue",
        ],
        sensor_check=_has_fuel_trim_anomaly,
        typical_cost_low=100,
        typical_cost_high=400,
        common_misdiagnoses=[
            "A MAF sensor can often be cleaned with MAF cleaner spray "
            "before replacement — a $10 fix instead of a $300 part.",
        ],
    ),
    "thermostat": RepairProfile(
        repair_id="thermostat",
        display_name="Thermostat replacement",
        supporting_dtc_patterns=[r"^P0128$"],
        supporting_sensor_conditions=[
            "P0128 (coolant temperature below thermostat regulating temperature)",
            "Coolant temperature reading higher than normal",
        ],
        sensor_check=_has_high_coolant,
        typical_cost_low=150,
        typical_cost_high=500,
        common_misdiagnoses=[
            "A failing water pump can cause the same symptoms. Both "
            "should be inspected.",
        ],
    ),
    "egr_valve": RepairProfile(
        repair_id="egr_valve",
        display_name="EGR valve replacement",
        supporting_dtc_patterns=[r"^P040[0-9]$"],
        supporting_sensor_conditions=[
            "P0400-P0409 EGR system fault codes",
        ],
        sensor_check=None,
        typical_cost_low=200,
        typical_cost_high=700,
        common_misdiagnoses=[
            "EGR valves can often be cleaned instead of replaced — ask "
            "if cleaning was attempted first.",
        ],
    ),
    "transmission": RepairProfile(
        repair_id="transmission",
        display_name="Transmission repair or replacement",
        supporting_dtc_patterns=[r"^P07[0-9]{2}$"],
        supporting_sensor_conditions=[
            "P07XX family transmission fault codes",
        ],
        sensor_check=None,
        typical_cost_low=1500,
        typical_cost_high=6000,
        common_misdiagnoses=[
            "Transmission quotes are the #1 place mechanics oversell. "
            "Get at least 2 independent opinions before authorizing "
            "any transmission work over $500.",
            "A fluid change or solenoid replacement is often mistaken "
            "for needing a full rebuild.",
        ],
    ),
}


# ══════════════════════════════════════════════════════════════════════════
# QUOTE TEXT CLASSIFICATION
# ══════════════════════════════════════════════════════════════════════════

REPAIR_KEYWORDS: Dict[str, str] = {
    "catalytic": "catalytic_converter",
    "cat converter": "catalytic_converter",
    "cat": "catalytic_converter",
    "o2 sensor": "oxygen_sensor",
    "oxygen sensor": "oxygen_sensor",
    "lambda sensor": "oxygen_sensor",
    "spark plug": "spark_plugs",
    "plugs": "spark_plugs",
    "ignition coil": "ignition_coil",
    "coil pack": "ignition_coil",
    "coil": "ignition_coil",
    "battery": "battery",
    "alternator": "alternator",
    "mass airflow": "mass_airflow_sensor",
    "maf sensor": "mass_airflow_sensor",
    "maf": "mass_airflow_sensor",
    "thermostat": "thermostat",
    "egr valve": "egr_valve",
    "egr": "egr_valve",
    "transmission": "transmission",
    "trans": "transmission",
    "tranny": "transmission",
}


def classify_quote(quote_text: str) -> Optional[str]:
    """Match a free-text quote against the repair catalog.

    Returns the repair_id of the most likely repair, or None.
    """
    text = quote_text.lower()
    # Match by longest keyword first to avoid "cat" matching "catalytic"
    for keyword in sorted(REPAIR_KEYWORDS.keys(), key=len, reverse=True):
        if keyword in text:
            return REPAIR_KEYWORDS[keyword]
    return None


def extract_price(quote_text: str) -> Optional[int]:
    """Extract a dollar amount from a quote."""
    # Handles "$1,800", "$1800", "1800 dollars", "cost me $2,500"
    matches = re.findall(r'\$?([\d,]+)(?:\s*(?:dollars|bucks|usd)?)?', quote_text)
    for m in matches:
        clean = m.replace(",", "")
        if clean.isdigit():
            val = int(clean)
            if 50 <= val <= 50000:  # Sanity range
                return val
    return None


# ══════════════════════════════════════════════════════════════════════════
# THE AUDITOR
# ══════════════════════════════════════════════════════════════════════════

def audit_quote(quote_text: str, obd_data: Dict[str, Any]) -> AuditResult:
    """Audit a mechanic's quote against actual OBD evidence.

    Args:
      quote_text: Free text of what the mechanic said. Example:
                  "You need a new catalytic converter, $1,800"
      obd_data:   OBD scan data (same shape as truth_detector expects)

    Returns:
      AuditResult with verdict, evidence, and a ShopScript the user can read
      at the counter.
    """
    now = datetime.utcnow().isoformat()

    # Step 1: Classify the quote
    repair_id = classify_quote(quote_text)
    quoted_price = extract_price(quote_text)

    if repair_id is None:
        return AuditResult(
            verdict=AuditVerdict.UNKNOWN_REPAIR,
            repair_id=None,
            repair_name=None,
            headline="I don't recognize this repair type yet",
            detail=(
                "LYLO could not match this quote to a known repair category. "
                "That does not mean it's wrong — it just means LYLO can't audit it. "
                "Ask the mechanic to explain what specific fault code or test result "
                "led to this recommendation."
            ),
            matching_evidence=[],
            missing_evidence=[],
            quoted_price=quoted_price,
            price_verdict=None,
            typical_range=None,
            shop_script=(
                "\"Can you show me the specific diagnostic code or test result "
                "that led to this recommendation? I want to make sure I understand "
                "the evidence before I approve the repair.\""
            ),
            confidence=0.0,
            audited_at=now,
        )

    profile = REPAIR_CATALOG[repair_id]

    # Step 2: Check OBD data against the repair profile
    dtcs = obd_data.get("dtcs", []) or []
    pending_dtcs = obd_data.get("pending_dtcs", []) or []
    all_codes = [str(c).upper() for c in (dtcs + pending_dtcs)]

    matching_codes = []
    for pattern in profile.supporting_dtc_patterns:
        for code in all_codes:
            if re.match(pattern, code):
                matching_codes.append(code)

    sensor_evidence = False
    sensor_note = None
    if profile.sensor_check is not None:
        try:
            sensor_evidence = profile.sensor_check(obd_data)
            if sensor_evidence:
                sensor_note = "Sensor data consistent with this repair"
        except Exception:
            sensor_evidence = False

    # Step 3: Determine the verdict
    matching_evidence = []
    missing_evidence = []

    if matching_codes:
        matching_evidence.append(
            f"Fault codes present: {', '.join(sorted(set(matching_codes)))}"
        )
    else:
        missing_evidence.append(
            "No fault codes matching this repair were found in the scan. "
            f"Expected: {', '.join(profile.supporting_dtc_patterns)}"
        )

    if sensor_evidence:
        matching_evidence.append(sensor_note)
    elif profile.sensor_check is not None:
        missing_evidence.append(
            "Sensor data does not show the pattern expected for this failure."
        )

    # Weight: codes are strong evidence, sensor data is moderate
    has_code_evidence = len(matching_codes) > 0
    has_sensor_evidence = sensor_evidence

    if has_code_evidence and has_sensor_evidence:
        verdict = AuditVerdict.SUPPORTED
        confidence = 0.90
    elif has_code_evidence:
        verdict = AuditVerdict.SUPPORTED
        confidence = 0.80
    elif has_sensor_evidence:
        verdict = AuditVerdict.PARTIALLY_SUPPORTED
        confidence = 0.55
    elif not any(obd_data.get(k) is not None for k in
                 ("dtcs", "pending_dtcs", "fuel_trim_long", "o2_voltage",
                  "battery_voltage", "coolant_temp")):
        verdict = AuditVerdict.INSUFFICIENT_DATA
        confidence = 0.0
    else:
        verdict = AuditVerdict.NOT_SUPPORTED
        confidence = 0.85  # High confidence in saying "this isn't supported"

    # Step 4: Evaluate the price (if extractable)
    price_verdict = None
    typical_range = None
    if profile.typical_cost_low and profile.typical_cost_high:
        typical_range = f"${profile.typical_cost_low} - ${profile.typical_cost_high}"
        if quoted_price is not None:
            if quoted_price < profile.typical_cost_low * 0.7:
                price_verdict = "low"  # suspiciously cheap
            elif quoted_price <= profile.typical_cost_high:
                price_verdict = "reasonable"
            elif quoted_price <= profile.typical_cost_high * 1.3:
                price_verdict = "high"
            else:
                price_verdict = "very_high"

    # Step 5: Build the headline, detail, and ShopScript
    headline, detail, shop_script = _build_messages(
        verdict=verdict,
        profile=profile,
        matching_codes=matching_codes,
        quoted_price=quoted_price,
        typical_range=typical_range,
        price_verdict=price_verdict,
    )

    return AuditResult(
        verdict=verdict,
        repair_id=repair_id,
        repair_name=profile.display_name,
        headline=headline,
        detail=detail,
        matching_evidence=matching_evidence,
        missing_evidence=missing_evidence,
        quoted_price=quoted_price,
        price_verdict=price_verdict,
        typical_range=typical_range,
        shop_script=shop_script,
        confidence=confidence,
        audited_at=now,
    )


def _build_messages(verdict, profile, matching_codes, quoted_price,
                    typical_range, price_verdict) -> Tuple[str, str, str]:
    """Build headline, detail paragraph, and ShopScript based on verdict."""
    name = profile.display_name

    if verdict == AuditVerdict.SUPPORTED:
        headline = f"Evidence supports: {name}"
        detail = (
            f"The OBD data shows evidence consistent with {name.lower()}. "
        )
        if matching_codes:
            detail += f"Matching fault codes: {', '.join(sorted(set(matching_codes)))}. "
        if typical_range:
            detail += f"Typical cost range for this repair: {typical_range}. "
        if price_verdict == "very_high":
            detail += (
                "The quoted price is significantly above the typical range. "
                "Get a second opinion before approving."
            )
        elif price_verdict == "high":
            detail += "The quoted price is on the high end of the typical range."
        elif price_verdict == "low":
            detail += (
                "The quoted price is below the typical range. This can sometimes "
                "indicate lower-quality parts — verify what parts are being used."
            )

        shop_script = (
            f"\"The scan I ran supports the {name.lower()} diagnosis. "
            f"I understand the typical range is {typical_range or 'known'}. "
            f"Can you show me the failed component or the specific test result? "
            f"I'd like to see the evidence before I approve the repair.\""
        )
        return headline, detail, shop_script

    if verdict == AuditVerdict.NOT_SUPPORTED:
        headline = f"Data does NOT support: {name}"
        detail = (
            f"The OBD scan does not show the evidence you'd expect to see "
            f"for {name.lower()}. There are no matching fault codes and "
            f"the sensor readings are not consistent with this diagnosis. "
        )
        if profile.common_misdiagnoses:
            detail += f"Note: {profile.common_misdiagnoses[0]}"

        shop_script = (
            f"\"I ran a scan on my car and I'm not seeing the codes or sensor "
            f"readings I'd expect for a {name.lower()} problem. "
            f"Can you show me the specific fault code or test result that led "
            f"to this diagnosis? I want to make sure I understand the evidence "
            f"before I authorize a {f'${quoted_price}' if quoted_price else 'major'} repair. "
            f"If you can't show me the evidence, I'd like to get a second opinion first.\""
        )
        return headline, detail, shop_script

    if verdict == AuditVerdict.PARTIALLY_SUPPORTED:
        headline = f"Partial evidence for: {name}"
        detail = (
            f"Some of the data is consistent with {name.lower()}, but the "
            f"strongest evidence (fault codes) is missing. This doesn't mean "
            f"the diagnosis is wrong, but it means you should ask for more "
            f"verification before approving. "
        )
        if profile.common_misdiagnoses:
            detail += f"Watch out: {profile.common_misdiagnoses[0]}"

        shop_script = (
            f"\"I see some symptoms that could point to a {name.lower()} issue, "
            f"but my scan didn't show the fault codes I'd expect. "
            f"Can you run a confirmation test to rule out other causes before "
            f"we commit to this repair?\""
        )
        return headline, detail, shop_script

    if verdict == AuditVerdict.INSUFFICIENT_DATA:
        headline = f"Can't verify: {name}"
        detail = (
            "There wasn't enough OBD scan data to audit this quote. "
            "Run a full scan (including fault codes, sensor readings, and "
            "freeze frame data) before asking LYLO to verify the diagnosis."
        )
        shop_script = (
            f"\"Before I approve this, can I get a copy of the diagnostic "
            f"codes and test results? I'd like to verify the diagnosis.\""
        )
        return headline, detail, shop_script

    # Unknown repair
    headline = "Could not identify this repair"
    detail = "LYLO did not recognize the repair mentioned in this quote."
    shop_script = (
        "\"Can you tell me the specific system or component being repaired? "
        "I want to understand exactly what work is being done.\""
    )
    return headline, detail, shop_script


def audit_result_to_dict(result: AuditResult) -> Dict:
    return {
        "verdict": result.verdict.value,
        "repair_id": result.repair_id,
        "repair_name": result.repair_name,
        "headline": result.headline,
        "detail": result.detail,
        "matching_evidence": result.matching_evidence,
        "missing_evidence": result.missing_evidence,
        "quoted_price": result.quoted_price,
        "price_verdict": result.price_verdict,
        "typical_range": result.typical_range,
        "shop_script": result.shop_script,
        "confidence": result.confidence,
        "audited_at": result.audited_at,
    }
