"""
The Good Neighbor Guard — LYLO Mechanic
Christopher Hughes · Sacramento, CA
AI Collaborators: Claude · GPT · Gemini · Groq
Truth · Safety · We Got Your Back

Demo scenarios: 10 real-world test cases covering
misleading codes, dangerous conditions, no-code failures,
incomplete data, and edge cases.
"""

from models.schemas import (
    OBDSessionInput, VehicleProfile, RawDTC, RawPIDValue,
    ReadinessMonitor, FreezeFrame, SymptomIntake
)

SCENARIOS = {

    "p0420_not_the_converter": {
        "label": "P0420 — Not What It Seems",
        "description": "Classic P0420 that looks like a dead converter — but isn't",
        "session": OBDSessionInput(
            adapter_id="OBDLink_MX+_DEMO",
            protocol="ISO 15765-4 CAN",
            connection_quality="stable",
            read_complete=True,
            vehicle_profile=VehicleProfile(
                year=2009, make="Honda", model="Accord", engine="2.4L I4",
                engine_type="port_injection", transmission="5AT",
                drive_type="FWD", odometer=147000
            ),
            raw_dtcs=[RawDTC(code="P0420", status="active")],
            raw_pids=[
                RawPIDValue("ENGINE_COOLANT_TEMP", "0x05", 197, "°F"),
                RawPIDValue("LONG_TERM_FUEL_TRIM_B1", "0x07", 4.7, "%"),
                RawPIDValue("SHORT_TERM_FUEL_TRIM_B1", "0x06", 2.1, "%"),
                RawPIDValue("ENGINE_RPM", "0x0C", 780, "rpm"),
                RawPIDValue("MAF_AIR_FLOW_RATE", "0x10", 4.2, "g/s"),
                RawPIDValue("BATTERY_VOLTAGE", "0x42", 14.1, "V"),
            ],
            readiness_monitors=[
                ReadinessMonitor("Catalyst", "complete"),
                ReadinessMonitor("O2 Sensor", "complete"),
                ReadinessMonitor("EVAP", "complete"),
            ],
        ),
        "symptoms": SymptomIntake(
            primary_category="warning_light_only",
            subcategories=["exhaust_smell", "ticking_cold"],
            when_it_happens=["cold_start"],
            severity="minor",
            frequency="occasional",
        ),
    },

    "flashing_misfire": {
        "label": "Flashing MIL — Active Misfire",
        "description": "Flashing check engine light, active catalyst-damaging misfire",
        "session": OBDSessionInput(
            adapter_id="OBDLink_MX+_DEMO",
            protocol="ISO 15765-4 CAN",
            connection_quality="stable",
            read_complete=True,
            vehicle_profile=VehicleProfile(
                year=2015, make="Toyota", model="Camry", engine="2.5L I4",
                odometer=89000
            ),
            raw_dtcs=[
                RawDTC(code="P0301", status="active"),
                RawDTC(code="P0420", status="pending"),
            ],
            raw_pids=[
                RawPIDValue("ENGINE_COOLANT_TEMP", "0x05", 203, "°F"),
                RawPIDValue("LONG_TERM_FUEL_TRIM_B1", "0x07", 6.2, "%"),
                RawPIDValue("ENGINE_RPM", "0x0C", 690, "rpm"),
                RawPIDValue("MAF_AIR_FLOW_RATE", "0x10", 3.8, "g/s"),
                RawPIDValue("BATTERY_VOLTAGE", "0x42", 13.9, "V"),
            ],
            readiness_monitors=[
                ReadinessMonitor("Catalyst", "complete"),
            ],
            freeze_frame=FreezeFrame(
                dtc_trigger="P0301",
                rpm=2400, speed=45, coolant_temp=207, load=68.2,
                fuel_trim_st=8.1, fuel_trim_lt=6.2
            ),
        ),
        "symptoms": SymptomIntake(
            primary_category="misfire",
            subcategories=["rough_idle", "hesitation"],
            when_it_happens=["idle", "under_load"],
            severity="significant",
            frequency="frequent",
            getting_worse=True,
        ),
        "extra_flags": ["FLASHING_MIL"],
    },

    "no_code_brake_danger": {
        "label": "No Codes — Brake Danger",
        "description": "OBD is clean but brake pedal is soft — OBD-II cannot see this",
        "session": OBDSessionInput(
            adapter_id="OBDLink_MX+_DEMO",
            protocol="ISO 15765-4 CAN",
            connection_quality="stable",
            read_complete=True,
            vehicle_profile=VehicleProfile(
                year=2012, make="Ford", model="F-150", engine="5.0L V8",
                odometer=112000
            ),
            raw_dtcs=[],
            raw_pids=[
                RawPIDValue("ENGINE_COOLANT_TEMP", "0x05", 194, "°F"),
                RawPIDValue("ENGINE_RPM", "0x0C", 810, "rpm"),
                RawPIDValue("BATTERY_VOLTAGE", "0x42", 14.2, "V"),
            ],
            readiness_monitors=[
                ReadinessMonitor("Catalyst", "complete"),
                ReadinessMonitor("O2 Sensor", "complete"),
                ReadinessMonitor("EVAP", "complete"),
            ],
        ),
        "symptoms": SymptomIntake(
            primary_category="brake_issue",
            subcategories=["soft_pedal", "brake_squeal"],
            when_it_happens=["braking"],
            severity="significant",
            frequency="constant",
            getting_worse=True,
        ),
    },

    "cleared_codes_incomplete_monitors": {
        "label": "Cleared Codes — Incomplete Monitors",
        "description": "Codes were cleared before scan — readiness monitors not yet complete",
        "session": OBDSessionInput(
            adapter_id="OBDLink_MX+_DEMO",
            protocol="ISO 15765-4 CAN",
            connection_quality="stable",
            read_complete=True,
            codes_cleared_before_scan=True,
            vehicle_profile=VehicleProfile(
                year=2018, make="Chevrolet", model="Silverado", engine="5.3L V8",
                odometer=67000
            ),
            raw_dtcs=[],
            raw_pids=[
                RawPIDValue("ENGINE_COOLANT_TEMP", "0x05", 198, "°F"),
                RawPIDValue("ENGINE_RPM", "0x0C", 760, "rpm"),
                RawPIDValue("BATTERY_VOLTAGE", "0x42", 14.0, "V"),
            ],
            readiness_monitors=[
                ReadinessMonitor("Catalyst", "incomplete"),
                ReadinessMonitor("O2 Sensor", "incomplete"),
                ReadinessMonitor("EVAP", "incomplete"),
                ReadinessMonitor("EGR", "incomplete"),
            ],
        ),
        "symptoms": SymptomIntake(
            primary_category="warning_light_only",
            severity="minor",
            frequency="once",
        ),
    },

    "low_voltage_cascade": {
        "label": "Low Voltage Cascade",
        "description": "Weak battery triggers 6 cascade codes — battery is the root cause",
        "session": OBDSessionInput(
            adapter_id="OBDLink_MX+_DEMO",
            protocol="ISO 15765-4 CAN",
            connection_quality="unstable",
            read_complete=True,
            vehicle_profile=VehicleProfile(
                year=2016, make="BMW", model="328i", engine="2.0L I4 Turbo",
                odometer=78000
            ),
            raw_dtcs=[
                RawDTC(code="P0562", status="active"),
                RawDTC(code="U0100", status="active"),
                RawDTC(code="P0601", status="active"),
                RawDTC(code="P1640", status="active"),
            ],
            raw_pids=[
                RawPIDValue("ENGINE_COOLANT_TEMP", "0x05", 193, "°F"),
                RawPIDValue("ENGINE_RPM", "0x0C", 820, "rpm"),
                RawPIDValue("BATTERY_VOLTAGE", "0x42", 11.8, "V"),
            ],
            readiness_monitors=[
                ReadinessMonitor("Catalyst", "incomplete"),
            ],
        ),
        "symptoms": SymptomIntake(
            primary_category="electrical",
            subcategories=["slow_crank"],
            when_it_happens=["cold_start"],
            severity="noticeable",
            frequency="occasional",
        ),
    },

    "overheating": {
        "label": "Overheating — Hot Engine",
        "description": "Coolant temp elevated with overheating symptoms",
        "session": OBDSessionInput(
            adapter_id="OBDLink_MX+_DEMO",
            protocol="ISO 15765-4 CAN",
            connection_quality="stable",
            read_complete=True,
            vehicle_profile=VehicleProfile(
                year=2011, make="Subaru", model="Outback", engine="2.5L H4",
                odometer=143000
            ),
            raw_dtcs=[RawDTC(code="P0217", status="active")],
            raw_pids=[
                RawPIDValue("ENGINE_COOLANT_TEMP", "0x05", 238, "°F"),
                RawPIDValue("ENGINE_RPM", "0x0C", 850, "rpm"),
                RawPIDValue("BATTERY_VOLTAGE", "0x42", 13.8, "V"),
                RawPIDValue("MAF_AIR_FLOW_RATE", "0x10", 3.9, "g/s"),
            ],
            readiness_monitors=[
                ReadinessMonitor("Catalyst", "complete"),
            ],
        ),
        "symptoms": SymptomIntake(
            primary_category="overheating",
            subcategories=["steam_from_hood"],
            when_it_happens=["highway", "under_load"],
            severity="severe",
            frequency="frequent",
            getting_worse=True,
        ),
    },

    "lean_condition": {
        "label": "Lean Condition — P0171",
        "description": "System lean — could be vacuum leak, MAF, or fuel delivery",
        "session": OBDSessionInput(
            adapter_id="OBDLink_MX+_DEMO",
            protocol="ISO 15765-4 CAN",
            connection_quality="stable",
            read_complete=True,
            vehicle_profile=VehicleProfile(
                year=2013, make="Nissan", model="Altima", engine="2.5L I4",
                odometer=94000
            ),
            raw_dtcs=[RawDTC(code="P0171", status="active")],
            raw_pids=[
                RawPIDValue("ENGINE_COOLANT_TEMP", "0x05", 201, "°F"),
                RawPIDValue("LONG_TERM_FUEL_TRIM_B1", "0x07", 18.8, "%"),
                RawPIDValue("SHORT_TERM_FUEL_TRIM_B1", "0x06", 7.4, "%"),
                RawPIDValue("ENGINE_RPM", "0x0C", 720, "rpm"),
                RawPIDValue("MAF_AIR_FLOW_RATE", "0x10", 1.9, "g/s"),
                RawPIDValue("BATTERY_VOLTAGE", "0x42", 14.0, "V"),
            ],
            readiness_monitors=[
                ReadinessMonitor("O2 Sensor", "complete"),
                ReadinessMonitor("Catalyst", "complete"),
            ],
        ),
        "symptoms": SymptomIntake(
            primary_category="rough_idle",
            subcategories=["hissing_sound"],
            when_it_happens=["idle", "cold_start"],
            severity="noticeable",
            frequency="constant",
        ),
    },

    "cam_timing_vvt": {
        "label": "VVT Cam Timing — P0011",
        "description": "Cam timing code with possible cold-start rattle",
        "session": OBDSessionInput(
            adapter_id="OBDLink_MX+_DEMO",
            protocol="ISO 15765-4 CAN",
            connection_quality="stable",
            read_complete=True,
            vehicle_profile=VehicleProfile(
                year=2010, make="Toyota", model="RAV4", engine="2.5L I4",
                odometer=127000
            ),
            raw_dtcs=[RawDTC(code="P0011", status="active")],
            raw_pids=[
                RawPIDValue("ENGINE_COOLANT_TEMP", "0x05", 199, "°F"),
                RawPIDValue("ENGINE_RPM", "0x0C", 790, "rpm"),
                RawPIDValue("LONG_TERM_FUEL_TRIM_B1", "0x07", 3.1, "%"),
                RawPIDValue("BATTERY_VOLTAGE", "0x42", 14.1, "V"),
            ],
            readiness_monitors=[ReadinessMonitor("Catalyst", "complete")],
        ),
        "symptoms": SymptomIntake(
            primary_category="rough_idle",
            subcategories=["cold_start_rattle", "engine_knock"],
            when_it_happens=["cold_start"],
            severity="noticeable",
            frequency="frequent",
            recent_repairs="Oil change last month — used 5W-30",
        ),
    },

    "manufacturer_specific_code": {
        "label": "Manufacturer-Specific Code — Unknown",
        "description": "A P1xxx code the system cannot fully interpret",
        "session": OBDSessionInput(
            adapter_id="OBDLink_MX+_DEMO",
            protocol="ISO 15765-4 CAN",
            connection_quality="stable",
            read_complete=True,
            vehicle_profile=VehicleProfile(
                year=2014, make="Honda", model="CR-V", engine="2.4L I4",
                odometer=88000
            ),
            raw_dtcs=[
                RawDTC(code="P1259", status="active"),
                RawDTC(code="P0171", status="pending"),
            ],
            raw_pids=[
                RawPIDValue("ENGINE_COOLANT_TEMP", "0x05", 196, "°F"),
                RawPIDValue("ENGINE_RPM", "0x0C", 740, "rpm"),
                RawPIDValue("LONG_TERM_FUEL_TRIM_B1", "0x07", 12.3, "%"),
                RawPIDValue("BATTERY_VOLTAGE", "0x42", 13.9, "V"),
            ],
            readiness_monitors=[ReadinessMonitor("O2 Sensor", "complete")],
        ),
        "symptoms": SymptomIntake(
            primary_category="rough_idle",
            when_it_happens=["idle"],
            severity="noticeable",
            frequency="occasional",
        ),
    },

    "no_code_vibration": {
        "label": "No Codes — Highway Vibration",
        "description": "Clean OBD data, vibration at highway speed — purely symptom-driven",
        "session": OBDSessionInput(
            adapter_id="OBDLink_MX+_DEMO",
            protocol="ISO 15765-4 CAN",
            connection_quality="stable",
            read_complete=True,
            vehicle_profile=VehicleProfile(
                year=2017, make="Toyota", model="Corolla", engine="1.8L I4",
                odometer=71000
            ),
            raw_dtcs=[],
            raw_pids=[
                RawPIDValue("ENGINE_COOLANT_TEMP", "0x05", 198, "°F"),
                RawPIDValue("ENGINE_RPM", "0x0C", 800, "rpm"),
                RawPIDValue("BATTERY_VOLTAGE", "0x42", 14.0, "V"),
                RawPIDValue("LONG_TERM_FUEL_TRIM_B1", "0x07", 1.6, "%"),
            ],
            readiness_monitors=[
                ReadinessMonitor("Catalyst", "complete"),
                ReadinessMonitor("O2 Sensor", "complete"),
                ReadinessMonitor("EVAP", "complete"),
            ],
        ),
        "symptoms": SymptomIntake(
            primary_category="vibration",
            subcategories=["steering_wheel_vibration", "vibration_turns"],
            when_it_happens=["highway"],
            severity="noticeable",
            frequency="frequent",
        ),
    },
}


def get_scenario(name: str) -> dict | None:
    return SCENARIOS.get(name)


def list_scenarios() -> list[dict]:
    return [
        {"id": k, "label": v["label"], "description": v["description"]}
        for k, v in SCENARIOS.items()
    ]
