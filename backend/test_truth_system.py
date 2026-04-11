"""
Veracore — The Good Neighbor Guard
Built by Christopher Hughes · Sacramento, CA
Created with the help of AI collaborators (Claude · GPT · Gemini · Groq)
Truth · Safety · We Got Your Back

Tests for Truth Detector, Failure Predictor, Event Black Box, and Quote Auditor.
"""

import unittest
from truth_detector import analyze_truth, TruthStatus, DeceptionSignal
from failure_predictor import analyze_health, HealthStatus
from event_blackbox import BlackBox, EventType
from quote_auditor import (
    audit_quote, classify_quote, extract_price,
    AuditVerdict, REPAIR_CATALOG,
)


# ═══════════════════════════════════════════════════════════════════════════
# TRUTH DETECTOR
# ═══════════════════════════════════════════════════════════════════════════

class TestTruthDetector(unittest.TestCase):

    def test_clean_vehicle(self):
        data = {
            "dtcs": [],
            "pending_dtcs": [],
            "monitors": {"catalyst": "ready", "evap": "ready", "o2_sensor": "ready"},
            "fuel_trim_long": 3.0,
            "o2_voltage": 0.7,
            "time_since_clear": None,
        }
        report = analyze_truth(data)
        self.assertEqual(report.status, TruthStatus.CLEAN)

    def test_recently_cleared_codes(self):
        data = {
            "dtcs": [],
            "pending_dtcs": [],
            "monitors": {},
            "time_since_clear": 5000,
        }
        report = analyze_truth(data)
        self.assertEqual(report.status, TruthStatus.INCONSISTENT)
        self.assertTrue(any(
            s.signal == DeceptionSignal.CODES_RECENTLY_CLEARED
            for s in report.signals
        ))

    def test_incomplete_monitors(self):
        data = {
            "dtcs": [],
            "pending_dtcs": [],
            "monitors": {
                "catalyst": "not_ready",
                "evap": "not_ready",
                "o2_sensor": "not_ready",
                "egr": "ready",
                "misfire": "ready",
            },
            "time_since_clear": None,
        }
        report = analyze_truth(data)
        self.assertTrue(any(
            s.signal == DeceptionSignal.MONITORS_INCOMPLETE
            for s in report.signals
        ))

    def test_fuel_trim_anomaly(self):
        data = {
            "dtcs": [],
            "pending_dtcs": [],
            "monitors": {},
            "fuel_trim_long": -18.0,
        }
        report = analyze_truth(data)
        self.assertTrue(any(
            s.signal == DeceptionSignal.FUEL_TRIM_ANOMALY
            for s in report.signals
        ))

    def test_flat_o2_sensor(self):
        data = {
            "dtcs": [],
            "pending_dtcs": [],
            "monitors": {},
            "o2_voltage": 0.45,
        }
        report = analyze_truth(data)
        self.assertTrue(any(
            s.signal == DeceptionSignal.O2_SENSOR_FLAT
            for s in report.signals
        ))

    def test_pending_codes_no_stored(self):
        data = {
            "dtcs": [],
            "pending_dtcs": ["P0420", "P0171"],
            "monitors": {},
        }
        report = analyze_truth(data)
        self.assertTrue(any(
            s.signal == DeceptionSignal.PENDING_CODES_WITH_NO_STORED
            for s in report.signals
        ))

    def test_freeze_frame_no_codes(self):
        data = {
            "dtcs": [],
            "pending_dtcs": [],
            "monitors": {},
            "freeze_frame": {"rpm": 2500, "speed": 45},
        }
        report = analyze_truth(data)
        self.assertTrue(any(
            s.signal == DeceptionSignal.FREEZE_FRAME_PRESENT_NO_CODES
            for s in report.signals
        ))

    def test_full_deception_scenario(self):
        """Lemon detector: everything looks suspicious."""
        data = {
            "dtcs": [],
            "pending_dtcs": ["P0301"],
            "monitors": {
                "catalyst": "not_ready",
                "evap": "not_ready",
                "o2_sensor": "not_ready",
                "egr": "not_ready",
                "misfire": "ready",
            },
            "fuel_trim_long": -22.0,
            "o2_voltage": 0.44,
            "time_since_clear": 3000,
            "freeze_frame": {"rpm": 800, "speed": 0},
        }
        report = analyze_truth(data)
        self.assertEqual(report.status, TruthStatus.INCONSISTENT)
        self.assertGreaterEqual(len(report.signals), 4)


# ═══════════════════════════════════════════════════════════════════════════
# FAILURE PREDICTOR
# ═══════════════════════════════════════════════════════════════════════════

class TestFailurePredictor(unittest.TestCase):

    def test_healthy_vehicle(self):
        data = {"battery_voltage": 12.6, "coolant_temp": 200, "fuel_trim_long": 2.0}
        report = analyze_health(data)
        self.assertEqual(report.overall_status, HealthStatus.STABLE)

    def test_weak_battery(self):
        data = {"battery_voltage": 11.5}
        report = analyze_health(data)
        self.assertEqual(report.overall_status, HealthStatus.CRITICAL)
        self.assertTrue(any(s.system == "battery" for s in report.signals))

    def test_moderate_battery_warning(self):
        data = {"battery_voltage": 12.0}
        report = analyze_health(data)
        self.assertEqual(report.overall_status, HealthStatus.WARNING)

    def test_overheating(self):
        data = {"coolant_temp": 235}
        report = analyze_health(data)
        self.assertEqual(report.overall_status, HealthStatus.CRITICAL)
        self.assertTrue(any(s.system == "cooling" for s in report.signals))

    def test_fuel_drift(self):
        data = {"fuel_trim_long": 25.0}
        report = analyze_health(data)
        self.assertTrue(any(s.system == "fuel_system" for s in report.signals))


# ═══════════════════════════════════════════════════════════════════════════
# EVENT BLACK BOX
# ═══════════════════════════════════════════════════════════════════════════

class TestEventBlackBox(unittest.TestCase):

    def test_hard_brake_detection(self):
        bb = BlackBox()
        bb.record_snapshot({"speed": 60, "rpm": 2500})
        event = bb.record_snapshot({"speed": 30, "rpm": 1200})
        self.assertIsNotNone(event)
        self.assertEqual(event.event_type, EventType.HARD_BRAKE)

    def test_overspeed_detection(self):
        bb = BlackBox()
        event = bb.record_snapshot({"speed": 95, "rpm": 4500})
        self.assertIsNotNone(event)
        self.assertEqual(event.event_type, EventType.OVERSPEED)

    def test_normal_driving_no_events(self):
        bb = BlackBox()
        event = bb.record_snapshot({"speed": 35, "rpm": 1800})
        self.assertIsNone(event)
        event = bb.record_snapshot({"speed": 37, "rpm": 1850})
        self.assertIsNone(event)

    def test_rapid_acceleration(self):
        bb = BlackBox()
        bb.record_snapshot({"speed": 20, "rpm": 2000})
        event = bb.record_snapshot({"speed": 40, "rpm": 4500})
        self.assertIsNotNone(event)
        self.assertEqual(event.event_type, EventType.RAPID_ACCELERATION)

    def test_engine_overrev(self):
        bb = BlackBox()
        event = bb.record_snapshot({"speed": 40, "rpm": 7000})
        self.assertIsNotNone(event)
        self.assertEqual(event.event_type, EventType.ENGINE_OVERREV)

    def test_impact_suspected(self):
        bb = BlackBox()
        bb.record_snapshot({"speed": 45, "rpm": 2000})
        event = bb.record_snapshot({"speed": 1, "rpm": 800})
        self.assertIsNotNone(event)
        self.assertEqual(event.event_type, EventType.IMPACT_SUSPECTED)

    def test_event_buffer_captures_context(self):
        bb = BlackBox()
        for i in range(10):
            bb.record_snapshot({"speed": 60, "rpm": 2500})
        event = bb.record_snapshot({"speed": 30, "rpm": 1200})
        self.assertIsNotNone(event)
        self.assertGreater(len(event.snapshots_before), 0)

    def test_get_events_returns_list(self):
        bb = BlackBox()
        bb.record_snapshot({"speed": 60, "rpm": 2500})
        bb.record_snapshot({"speed": 30, "rpm": 1200})
        events = bb.get_events()
        self.assertIsInstance(events, list)
        self.assertEqual(len(events), 1)

    def test_clear_resets_everything(self):
        bb = BlackBox()
        bb.record_snapshot({"speed": 95, "rpm": 4500})
        bb.clear()
        self.assertEqual(len(bb.events), 0)
        self.assertEqual(len(bb.buffer), 0)


# ═══════════════════════════════════════════════════════════════════════════
# QUOTE AUDITOR (the bonus layer)
# ═══════════════════════════════════════════════════════════════════════════

class TestQuoteClassification(unittest.TestCase):

    def test_classify_catalytic(self):
        self.assertEqual(classify_quote("you need a new catalytic converter"), "catalytic_converter")
        self.assertEqual(classify_quote("cat converter is bad"), "catalytic_converter")

    def test_classify_o2_sensor(self):
        self.assertEqual(classify_quote("your o2 sensor is dead"), "oxygen_sensor")
        self.assertEqual(classify_quote("oxygen sensor replacement needed"), "oxygen_sensor")

    def test_classify_battery(self):
        self.assertEqual(classify_quote("battery replacement, $200"), "battery")

    def test_classify_transmission(self):
        self.assertEqual(classify_quote("your transmission is shot"), "transmission")
        self.assertEqual(classify_quote("tranny needs rebuild"), "transmission")

    def test_classify_unknown(self):
        self.assertIsNone(classify_quote("something vague needs fixing"))

    def test_extract_price_dollar_sign(self):
        self.assertEqual(extract_price("will cost you $1,800"), 1800)

    def test_extract_price_no_dollar(self):
        self.assertEqual(extract_price("about 500 bucks"), 500)

    def test_extract_price_none(self):
        self.assertIsNone(extract_price("we need to fix your car"))


class TestQuoteAuditor(unittest.TestCase):
    """The 4th layer — auditing mechanic claims against actual evidence."""

    def test_supported_catalytic_quote(self):
        """Quote matches the data → SUPPORTED."""
        result = audit_quote(
            "You need a new catalytic converter, $1,500",
            {
                "dtcs": ["P0420"],
                "pending_dtcs": [],
                "fuel_trim_long": 5.0,
            }
        )
        self.assertEqual(result.verdict, AuditVerdict.SUPPORTED)
        self.assertEqual(result.repair_id, "catalytic_converter")
        self.assertEqual(result.quoted_price, 1500)
        self.assertEqual(result.price_verdict, "reasonable")

    def test_NOT_supported_catalytic_quote(self):
        """THE MECHANIC KILLER TEST.

        Mechanic says cat converter, $1,800. Scan shows NO P0420, NO P0430,
        NO O2 anomaly. Data does not support the diagnosis.
        """
        result = audit_quote(
            "Your catalytic converter is going bad, it'll be $1,800",
            {
                "dtcs": [],
                "pending_dtcs": [],
                "fuel_trim_long": 3.0,
                "o2_voltage": 0.7,
            }
        )
        self.assertEqual(result.verdict, AuditVerdict.NOT_SUPPORTED)
        self.assertEqual(result.quoted_price, 1800)
        self.assertIn("NOT support", result.headline)
        # Shop script must tell the user how to push back
        self.assertIn("scan", result.shop_script.lower())

    def test_overpriced_supported_quote(self):
        """Quote is legit but VERY overpriced."""
        result = audit_quote(
            "O2 sensor replacement, $1,500",
            {"dtcs": ["P0135"], "pending_dtcs": []}
        )
        self.assertEqual(result.verdict, AuditVerdict.SUPPORTED)
        self.assertEqual(result.price_verdict, "very_high")

    def test_battery_quote_with_low_voltage(self):
        """Battery quote with evidence → SUPPORTED via sensor check."""
        result = audit_quote(
            "Battery needs replacement, $180",
            {"battery_voltage": 11.5, "dtcs": []}
        )
        # Sensor check fires → partial or supported depending on codes
        self.assertIn(result.verdict, (AuditVerdict.SUPPORTED, AuditVerdict.PARTIALLY_SUPPORTED))

    def test_transmission_quote_no_codes(self):
        """Transmission quote without P07XX codes → should NOT be supported."""
        result = audit_quote(
            "Your transmission is shot, $4,500",
            {"dtcs": [], "pending_dtcs": []}
        )
        self.assertEqual(result.verdict, AuditVerdict.NOT_SUPPORTED)
        # Transmission work has known misdiagnosis warnings
        self.assertIn("transmission", result.repair_name.lower())

    def test_unknown_repair_graceful(self):
        """Unknown repair → returns UNKNOWN_REPAIR with helpful shop script."""
        result = audit_quote(
            "Some weird thing needs replacing",
            {"dtcs": ["P0420"]}
        )
        self.assertEqual(result.verdict, AuditVerdict.UNKNOWN_REPAIR)
        self.assertIsNotNone(result.shop_script)

    def test_insufficient_data(self):
        """Empty OBD data → INSUFFICIENT_DATA."""
        result = audit_quote(
            "Catalytic converter, $1,500",
            {}
        )
        self.assertEqual(result.verdict, AuditVerdict.INSUFFICIENT_DATA)

    def test_shop_script_always_present(self):
        """Every audit result must include a shop_script the user can read."""
        scenarios = [
            ("catalytic converter, $1500", {"dtcs": ["P0420"]}),
            ("catalytic converter, $1500", {"dtcs": []}),
            ("unknown repair", {"dtcs": []}),
            ("cat converter", {}),
        ]
        for quote, data in scenarios:
            result = audit_quote(quote, data)
            self.assertIsNotNone(result.shop_script)
            self.assertGreater(len(result.shop_script), 20)

    def test_pending_codes_also_count_as_evidence(self):
        """Pending (unconfirmed) codes should still count as evidence."""
        result = audit_quote(
            "Oxygen sensor replacement",
            {"dtcs": [], "pending_dtcs": ["P0135"]}
        )
        self.assertEqual(result.verdict, AuditVerdict.SUPPORTED)

    def test_repair_catalog_completeness(self):
        """Every repair in the catalog has at least one supporting pattern."""
        for repair_id, profile in REPAIR_CATALOG.items():
            self.assertGreater(len(profile.supporting_dtc_patterns), 0,
                               f"{repair_id} has no DTC patterns")
            self.assertGreater(len(profile.supporting_sensor_conditions), 0,
                               f"{repair_id} has no sensor conditions")
            self.assertGreater(len(profile.display_name), 0)


# ═══════════════════════════════════════════════════════════════════════════
# INTEGRATION: All 4 systems together
# ═══════════════════════════════════════════════════════════════════════════

class TestTruthSystemIntegration(unittest.TestCase):

    def test_clean_scan_all_systems_agree(self):
        data = {
            "dtcs": [],
            "pending_dtcs": [],
            "monitors": {"catalyst": "ready", "evap": "ready"},
            "fuel_trim_long": 2.0,
            "o2_voltage": 0.7,
            "battery_voltage": 12.6,
            "coolant_temp": 200,
        }
        truth = analyze_truth(data)
        health = analyze_health(data)
        self.assertEqual(truth.status, TruthStatus.CLEAN)
        self.assertEqual(health.overall_status, HealthStatus.STABLE)

    def test_hidden_problems_scenario(self):
        """Seller says 'no issues' but scan reveals they cleared codes."""
        data = {
            "dtcs": [],
            "pending_dtcs": [],
            "monitors": {
                "catalyst": "not_ready", "evap": "not_ready",
                "o2_sensor": "not_ready", "egr": "not_ready", "misfire": "ready"
            },
            "time_since_clear": 2000,
            "battery_voltage": 12.5,
            "coolant_temp": 200,
        }
        truth = analyze_truth(data)
        self.assertEqual(truth.status, TruthStatus.INCONSISTENT)
        # User can ALSO audit a quote in this state
        result = audit_quote(
            "Seller says no issues, wants $8,000",
            data
        )
        # The quote is for "no issues" which doesn't classify to a repair
        self.assertEqual(result.verdict, AuditVerdict.UNKNOWN_REPAIR)

    def test_mechanic_killer_end_to_end(self):
        """The full scenario this whole system exists to catch.

        Vehicle is actually fine. Mechanic tries to sell a fake $1,800 cat job.
        Truth Detector: CLEAN.
        Failure Predictor: STABLE.
        Quote Auditor: NOT_SUPPORTED — push back.
        """
        data = {
            "dtcs": [],
            "pending_dtcs": [],
            "monitors": {"catalyst": "ready", "evap": "ready", "o2_sensor": "ready"},
            "fuel_trim_long": 3.0,
            "o2_voltage": 0.7,
            "battery_voltage": 12.6,
            "coolant_temp": 200,
        }
        truth = analyze_truth(data)
        health = analyze_health(data)
        audit = audit_quote("You need a new catalytic converter, $1,800", data)

        self.assertEqual(truth.status, TruthStatus.CLEAN)
        self.assertEqual(health.overall_status, HealthStatus.STABLE)
        self.assertEqual(audit.verdict, AuditVerdict.NOT_SUPPORTED)
        self.assertEqual(audit.quoted_price, 1800)
        self.assertIn("scan", audit.shop_script.lower())


if __name__ == "__main__":
    unittest.main()
