"""Trigger detection for teaching brief generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from luca.utils.logging import get_logger

logger = get_logger("student.triggers")


class TriggerType(Enum):
    """Types of triggers that can fire."""

    ERROR_PATTERN = "error_pattern"
    MASTERY_THRESHOLD = "mastery_threshold"
    RESPONSE_SPEED_CHANGE = "response_speed_change"
    CONCEPT_TRANSITION = "concept_transition"


@dataclass
class TriggerEvent:
    """A triggered event that should generate a teaching brief."""

    trigger_type: TriggerType
    concept_id: str
    timestamp: datetime = field(default_factory=datetime.now)
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for persistence."""
        return {
            "trigger_type": self.trigger_type.value,
            "concept_id": self.concept_id,
            "timestamp": self.timestamp.isoformat(),
            "details": self.details,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TriggerEvent:
        """Create from dictionary."""
        return cls(
            trigger_type=TriggerType(data["trigger_type"]),
            concept_id=data["concept_id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            details=data.get("details", {}),
        )


class TriggerDetector:
    """Detects state changes that should trigger teaching brief generation.

    Triggers fire on:
    - Mastery crossing thresholds (0.7 up/down, 0.3 down)
    - Response speed changes (50%+ change in avg response time)
    - Concept transitions (moving to a new concept)
    """

    # Mastery thresholds
    HIGH_MASTERY_THRESHOLD = 0.7
    LOW_MASTERY_THRESHOLD = 0.3

    # Response speed change threshold (50%)
    SPEED_CHANGE_THRESHOLD = 0.5

    def __init__(self) -> None:
        # Track previous mastery levels to detect threshold crossings
        self._prev_mastery: dict[str, float] = {}
        # Track previous average response times per concept
        self._prev_avg_response_time: dict[str, float] = {}
        # Track which concepts have been visited
        self._visited_concepts: set[str] = set()

    def check_mastery_threshold(
        self, concept_id: str, old_mastery: float, new_mastery: float
    ) -> TriggerEvent | None:
        """Check if mastery crossed a significant threshold.

        Fires when:
        - Crossing 0.7 upward (approaching mastery)
        - Crossing 0.7 downward (losing mastery)
        - Crossing 0.3 downward (struggling)
        """
        high = self.HIGH_MASTERY_THRESHOLD
        low = self.LOW_MASTERY_THRESHOLD

        # Crossing 0.7 upward
        if old_mastery < high <= new_mastery:
            logger.info(f"Mastery threshold crossed upward for {concept_id}: {new_mastery:.2f}")
            return TriggerEvent(
                trigger_type=TriggerType.MASTERY_THRESHOLD,
                concept_id=concept_id,
                details={
                    "direction": "up",
                    "threshold": high,
                    "old_mastery": old_mastery,
                    "new_mastery": new_mastery,
                },
            )

        # Crossing 0.7 downward
        if old_mastery >= high > new_mastery:
            logger.info(f"Mastery threshold crossed downward for {concept_id}: {new_mastery:.2f}")
            return TriggerEvent(
                trigger_type=TriggerType.MASTERY_THRESHOLD,
                concept_id=concept_id,
                details={
                    "direction": "down",
                    "threshold": high,
                    "old_mastery": old_mastery,
                    "new_mastery": new_mastery,
                },
            )

        # Crossing 0.3 downward
        if old_mastery >= low > new_mastery:
            logger.info(f"Mastery dropped below struggling threshold for {concept_id}: {new_mastery:.2f}")
            return TriggerEvent(
                trigger_type=TriggerType.MASTERY_THRESHOLD,
                concept_id=concept_id,
                details={
                    "direction": "down",
                    "threshold": low,
                    "old_mastery": old_mastery,
                    "new_mastery": new_mastery,
                },
            )

        return None

    def check_response_speed(
        self, concept_id: str, old_avg_time: float, new_avg_time: float
    ) -> TriggerEvent | None:
        """Check if response speed changed significantly.

        Fires when average response time changes by 50% or more.
        """
        if old_avg_time <= 0:
            return None

        change_ratio = abs(new_avg_time - old_avg_time) / old_avg_time

        if change_ratio >= self.SPEED_CHANGE_THRESHOLD:
            direction = "slower" if new_avg_time > old_avg_time else "faster"
            logger.info(
                f"Response speed change for {concept_id}: {direction} "
                f"({old_avg_time:.2f}s -> {new_avg_time:.2f}s, {change_ratio:.0%} change)"
            )
            return TriggerEvent(
                trigger_type=TriggerType.RESPONSE_SPEED_CHANGE,
                concept_id=concept_id,
                details={
                    "direction": direction,
                    "old_avg_time": old_avg_time,
                    "new_avg_time": new_avg_time,
                    "change_ratio": change_ratio,
                },
            )

        return None

    def check_concept_transition(
        self, old_concept_id: str | None, new_concept_id: str
    ) -> TriggerEvent | None:
        """Check if transitioning to a new concept.

        Fires when moving to a concept that hasn't been visited yet.
        """
        if new_concept_id in self._visited_concepts:
            return None

        self._visited_concepts.add(new_concept_id)

        logger.info(f"Concept transition: {old_concept_id} -> {new_concept_id}")
        return TriggerEvent(
            trigger_type=TriggerType.CONCEPT_TRANSITION,
            concept_id=new_concept_id,
            details={
                "from_concept": old_concept_id,
                "to_concept": new_concept_id,
            },
        )

    def mark_concept_visited(self, concept_id: str) -> None:
        """Mark a concept as visited (used when loading from persistence)."""
        self._visited_concepts.add(concept_id)

    def update_prev_mastery(self, concept_id: str, mastery: float) -> None:
        """Update the previous mastery level for a concept."""
        self._prev_mastery[concept_id] = mastery

    def get_prev_mastery(self, concept_id: str) -> float | None:
        """Get the previous mastery level for a concept."""
        return self._prev_mastery.get(concept_id)

    def update_prev_response_time(self, concept_id: str, avg_time: float) -> None:
        """Update the previous average response time for a concept."""
        self._prev_avg_response_time[concept_id] = avg_time

    def get_prev_response_time(self, concept_id: str) -> float | None:
        """Get the previous average response time for a concept."""
        return self._prev_avg_response_time.get(concept_id)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for persistence."""
        return {
            "prev_mastery": self._prev_mastery,
            "prev_avg_response_time": self._prev_avg_response_time,
            "visited_concepts": list(self._visited_concepts),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TriggerDetector:
        """Create from dictionary."""
        detector = cls()
        detector._prev_mastery = data.get("prev_mastery", {})
        detector._prev_avg_response_time = data.get("prev_avg_response_time", {})
        detector._visited_concepts = set(data.get("visited_concepts", []))
        return detector
