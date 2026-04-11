"""
Veracore — The Good Neighbor Guard
Built by Christopher Hughes · Sacramento, CA
Created with the help of AI collaborators (Claude · GPT · Gemini · Groq)
Truth · Safety · We Got Your Back

EVENT BLACK BOX — Drive Event Recorder
Captures what actually happened before and after significant events.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any
from datetime import datetime
from enum import Enum
from collections import deque


class EventType(Enum):
    HARD_BRAKE = "hard_brake"
    RAPID_ACCELERATION = "rapid_acceleration"
    OVERSPEED = "overspeed"
    ENGINE_OVERREV = "engine_overrev"
    IMPACT_SUSPECTED = "impact_suspected"
    STALL = "stall"


@dataclass
class DataSnapshot:
    """A single moment of vehicle data."""
    timestamp: str
    rpm: Optional[int] = None
    speed_mph: Optional[float] = None
    throttle_pct: Optional[float] = None
    engine_load_pct: Optional[float] = None
    coolant_temp_f: Optional[float] = None
    brake_active: Optional[bool] = None


@dataclass
class EventRecord:
    """A recorded vehicle event with surrounding context."""
    event_type: EventType
    triggered_at: str
    human_summary: str
    severity: str                       # "low", "medium", "high"
    snapshots_before: List[DataSnapshot]  # Data leading up to event
    snapshots_after: List[DataSnapshot]   # Data after event
    peak_values: Dict[str, Any]         # Notable peak readings


class BlackBox:
    """
    Rolling buffer that captures vehicle data and detects significant events.

    Keeps the last 30 seconds of data in a circular buffer.
    When a triggering event is detected, it saves the buffer contents
    as a permanent event record.
    """

    def __init__(self, buffer_size: int = 30):
        self.buffer = deque(maxlen=buffer_size)
        self.events: List[EventRecord] = []
        self.last_speed = None
        self.last_rpm = None

    def record_snapshot(self, data: Dict[str, Any]) -> Optional[EventRecord]:
        """
        Record a data snapshot and check for triggering events.

        Call this every ~1 second with current OBD readings.
        Returns an EventRecord if a significant event was detected.
        """
        snapshot = DataSnapshot(
            timestamp=datetime.utcnow().isoformat(),
            rpm=data.get("rpm"),
            speed_mph=data.get("speed"),
            throttle_pct=data.get("throttle_position"),
            engine_load_pct=data.get("engine_load"),
            coolant_temp_f=data.get("coolant_temp"),
            brake_active=data.get("brake_active"),
        )

        self.buffer.append(snapshot)
        event = self._check_triggers(snapshot)

        if event:
            self.events.append(event)

        self.last_speed = snapshot.speed_mph
        self.last_rpm = snapshot.rpm

        return event

    def _check_triggers(self, current: DataSnapshot) -> Optional[EventRecord]:
        """Check if current readings trigger an event.

        Order matters: more severe events are checked first so a "coming
        to a stop at 40 mph" event gets classified as IMPACT_SUSPECTED
        (the more serious interpretation) rather than HARD_BRAKE.
        """

        # IMPACT SUSPECTED: Speed drops to near zero from above 30 in one second
        # Checked first so impact is not misclassified as hard brake
        if (current.speed_mph is not None and current.speed_mph < 2
                and self.last_speed is not None and self.last_speed > 30):
            return self._create_event(
                EventType.IMPACT_SUSPECTED,
                f"Possible impact: vehicle went from {self.last_speed:.0f} mph to "
                f"near stop in approximately 1 second",
                severity="high"
            )

        # HARD BRAKE: Speed drops more than 20 mph in one second
        if (self.last_speed is not None and current.speed_mph is not None
                and self.last_speed - current.speed_mph > 20):
            return self._create_event(
                EventType.HARD_BRAKE,
                f"Hard braking detected: speed dropped from {self.last_speed:.0f} mph "
                f"to {current.speed_mph:.0f} mph",
                severity="high" if self.last_speed - current.speed_mph > 40 else "medium"
            )

        # RAPID ACCELERATION: Speed increases more than 15 mph in one second
        if (self.last_speed is not None and current.speed_mph is not None
                and current.speed_mph - self.last_speed > 15):
            return self._create_event(
                EventType.RAPID_ACCELERATION,
                f"Rapid acceleration detected: speed jumped from {self.last_speed:.0f} mph "
                f"to {current.speed_mph:.0f} mph",
                severity="medium"
            )

        # OVERSPEED: Above 90 mph
        if current.speed_mph is not None and current.speed_mph > 90:
            return self._create_event(
                EventType.OVERSPEED,
                f"Vehicle speed reached {current.speed_mph:.0f} mph",
                severity="high"
            )

        # ENGINE OVERREV: RPM above 6500
        if current.rpm is not None and current.rpm > 6500:
            return self._create_event(
                EventType.ENGINE_OVERREV,
                f"Engine RPM reached {current.rpm}",
                severity="medium"
            )

        return None

    def _create_event(self, event_type: EventType, summary: str,
                      severity: str) -> EventRecord:
        """Create an event record with buffer context."""
        buffer_list = list(self.buffer)
        split = max(0, len(buffer_list) - 5)

        return EventRecord(
            event_type=event_type,
            triggered_at=datetime.utcnow().isoformat(),
            human_summary=summary,
            severity=severity,
            snapshots_before=buffer_list[:split],
            snapshots_after=buffer_list[split:],
            peak_values={
                "max_speed": max((s.speed_mph or 0) for s in buffer_list),
                "max_rpm": max((s.rpm or 0) for s in buffer_list),
                "max_engine_load": max((s.engine_load_pct or 0) for s in buffer_list),
            }
        )

    def get_events(self) -> List[Dict]:
        """Get all recorded events as dictionaries."""
        return [
            {
                "type": e.event_type.value,
                "triggered_at": e.triggered_at,
                "summary": e.human_summary,
                "severity": e.severity,
                "peak_values": e.peak_values,
                "snapshot_count": len(e.snapshots_before) + len(e.snapshots_after),
            }
            for e in self.events
        ]

    def clear(self):
        """Clear all events and buffer."""
        self.buffer.clear()
        self.events.clear()
        self.last_speed = None
        self.last_rpm = None
