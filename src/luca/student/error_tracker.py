"""Error pattern tracking for trigger-based teaching briefs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from luca.utils.logging import get_logger

logger = get_logger("student.error_tracker")


@dataclass
class ErrorOccurrence:
    """A single occurrence of an error."""

    error_type: str
    concept_id: str
    timestamp: datetime = field(default_factory=datetime.now)
    student_response: str = ""
    expected_response: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for persistence."""
        return {
            "error_type": self.error_type,
            "concept_id": self.concept_id,
            "timestamp": self.timestamp.isoformat(),
            "student_response": self.student_response,
            "expected_response": self.expected_response,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ErrorOccurrence:
        """Create from dictionary."""
        return cls(
            error_type=data["error_type"],
            concept_id=data["concept_id"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            student_response=data.get("student_response", ""),
            expected_response=data.get("expected_response", ""),
        )


@dataclass
class ErrorPattern:
    """A pattern of repeated errors."""

    error_type: str
    concept_id: str
    occurrences: list[ErrorOccurrence] = field(default_factory=list)
    triggered: bool = False

    @property
    def count(self) -> int:
        """Get the number of occurrences."""
        return len(self.occurrences)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for persistence."""
        return {
            "error_type": self.error_type,
            "concept_id": self.concept_id,
            "occurrences": [o.to_dict() for o in self.occurrences],
            "triggered": self.triggered,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ErrorPattern:
        """Create from dictionary."""
        return cls(
            error_type=data["error_type"],
            concept_id=data["concept_id"],
            occurrences=[ErrorOccurrence.from_dict(o) for o in data.get("occurrences", [])],
            triggered=data.get("triggered", False),
        )


class ErrorTracker:
    """Tracks error patterns and detects when triggers should fire.

    An error pattern triggers when the same error type occurs 3 times
    for the same concept. The trigger only fires once per pattern.
    """

    TRIGGER_THRESHOLD = 3

    def __init__(self) -> None:
        # Key: (error_type, concept_id) -> ErrorPattern
        self._patterns: dict[tuple[str, str], ErrorPattern] = {}

    def record_error(
        self,
        error_type: str,
        concept_id: str,
        student_response: str = "",
        expected_response: str = "",
    ) -> bool:
        """Record an error occurrence.

        Args:
            error_type: Type identifier for the error.
            concept_id: The concept where the error occurred.
            student_response: What the student said.
            expected_response: What was expected.

        Returns:
            True if this is the 3rd occurrence (trigger fires), False otherwise.
        """
        key = (error_type, concept_id)
        occurrence = ErrorOccurrence(
            error_type=error_type,
            concept_id=concept_id,
            student_response=student_response,
            expected_response=expected_response,
        )

        if key not in self._patterns:
            self._patterns[key] = ErrorPattern(
                error_type=error_type,
                concept_id=concept_id,
            )

        pattern = self._patterns[key]
        pattern.occurrences.append(occurrence)

        # Check if we hit the threshold and haven't triggered yet
        if pattern.count >= self.TRIGGER_THRESHOLD and not pattern.triggered:
            pattern.triggered = True
            logger.info(
                f"Error pattern triggered: {error_type} for {concept_id} "
                f"({pattern.count} occurrences)"
            )
            return True

        return False

    def get_error_patterns(self) -> list[ErrorPattern]:
        """Get all tracked error patterns."""
        return list(self._patterns.values())

    def get_triggered_patterns(self) -> list[ErrorPattern]:
        """Get only patterns that have triggered."""
        return [p for p in self._patterns.values() if p.triggered]

    def get_pattern(self, error_type: str, concept_id: str) -> ErrorPattern | None:
        """Get a specific error pattern."""
        return self._patterns.get((error_type, concept_id))

    def reset_pattern(self, error_type: str, concept_id: str) -> None:
        """Reset a pattern's trigger status (allows it to fire again)."""
        key = (error_type, concept_id)
        if key in self._patterns:
            self._patterns[key].triggered = False

    def clear(self) -> None:
        """Clear all tracked patterns."""
        self._patterns.clear()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for persistence."""
        return {
            "patterns": [p.to_dict() for p in self._patterns.values()],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ErrorTracker:
        """Create from dictionary."""
        tracker = cls()
        for p_data in data.get("patterns", []):
            pattern = ErrorPattern.from_dict(p_data)
            tracker._patterns[(pattern.error_type, pattern.concept_id)] = pattern
        return tracker
