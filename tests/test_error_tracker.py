"""Tests for error tracking functionality."""

import pytest
from datetime import datetime

from luca.student.error_tracker import ErrorOccurrence, ErrorPattern, ErrorTracker


class TestErrorOccurrence:
    """Tests for ErrorOccurrence dataclass."""

    def test_to_dict(self):
        """Test serialization to dict."""
        occurrence = ErrorOccurrence(
            error_type="gender_agreement",
            concept_id="articles_1",
            student_response="el agua",
            expected_response="la agua",
        )

        data = occurrence.to_dict()

        assert data["error_type"] == "gender_agreement"
        assert data["concept_id"] == "articles_1"
        assert data["student_response"] == "el agua"
        assert "timestamp" in data

    def test_from_dict(self):
        """Test deserialization from dict."""
        data = {
            "error_type": "gender_agreement",
            "concept_id": "articles_1",
            "timestamp": "2024-01-15T10:30:00",
            "student_response": "el agua",
            "expected_response": "la agua",
        }

        occurrence = ErrorOccurrence.from_dict(data)

        assert occurrence.error_type == "gender_agreement"
        assert occurrence.concept_id == "articles_1"
        assert occurrence.student_response == "el agua"


class TestErrorPattern:
    """Tests for ErrorPattern dataclass."""

    def test_count_property(self):
        """Test count returns number of occurrences."""
        pattern = ErrorPattern(
            error_type="gender_agreement",
            concept_id="articles_1",
        )

        assert pattern.count == 0

        pattern.occurrences.append(
            ErrorOccurrence("gender_agreement", "articles_1")
        )
        assert pattern.count == 1

    def test_serialization_roundtrip(self):
        """Test to_dict and from_dict preserve data."""
        pattern = ErrorPattern(
            error_type="gender_agreement",
            concept_id="articles_1",
            triggered=True,
        )
        pattern.occurrences.append(
            ErrorOccurrence("gender_agreement", "articles_1", student_response="el")
        )

        data = pattern.to_dict()
        restored = ErrorPattern.from_dict(data)

        assert restored.error_type == "gender_agreement"
        assert restored.triggered is True
        assert len(restored.occurrences) == 1
        assert restored.occurrences[0].student_response == "el"


class TestErrorTracker:
    """Tests for ErrorTracker class."""

    def test_first_error_does_not_trigger(self):
        """Test that first occurrence doesn't trigger."""
        tracker = ErrorTracker()

        triggered = tracker.record_error(
            error_type="gender_agreement",
            concept_id="articles_1",
        )

        assert triggered is False

    def test_second_error_does_not_trigger(self):
        """Test that second occurrence doesn't trigger."""
        tracker = ErrorTracker()

        tracker.record_error("gender_agreement", "articles_1")
        triggered = tracker.record_error("gender_agreement", "articles_1")

        assert triggered is False

    def test_third_error_triggers(self):
        """Test that third occurrence triggers."""
        tracker = ErrorTracker()

        tracker.record_error("gender_agreement", "articles_1")
        tracker.record_error("gender_agreement", "articles_1")
        triggered = tracker.record_error("gender_agreement", "articles_1")

        assert triggered is True

    def test_trigger_only_fires_once(self):
        """Test that trigger only fires once per pattern."""
        tracker = ErrorTracker()

        # First 3 occurrences
        tracker.record_error("gender_agreement", "articles_1")
        tracker.record_error("gender_agreement", "articles_1")
        first_trigger = tracker.record_error("gender_agreement", "articles_1")

        # Fourth occurrence
        fourth_trigger = tracker.record_error("gender_agreement", "articles_1")

        assert first_trigger is True
        assert fourth_trigger is False

    def test_different_concepts_tracked_separately(self):
        """Test that different concepts have separate patterns."""
        tracker = ErrorTracker()

        # 3 errors on concept_1
        tracker.record_error("gender_agreement", "concept_1")
        tracker.record_error("gender_agreement", "concept_1")
        trigger_1 = tracker.record_error("gender_agreement", "concept_1")

        # 2 errors on concept_2 (shouldn't trigger yet)
        tracker.record_error("gender_agreement", "concept_2")
        trigger_2 = tracker.record_error("gender_agreement", "concept_2")

        assert trigger_1 is True
        assert trigger_2 is False

    def test_different_error_types_tracked_separately(self):
        """Test that different error types have separate patterns."""
        tracker = ErrorTracker()

        # 3 gender errors
        tracker.record_error("gender_agreement", "articles_1")
        tracker.record_error("gender_agreement", "articles_1")
        gender_trigger = tracker.record_error("gender_agreement", "articles_1")

        # 2 conjugation errors (shouldn't trigger yet)
        tracker.record_error("verb_conjugation", "articles_1")
        conj_trigger = tracker.record_error("verb_conjugation", "articles_1")

        assert gender_trigger is True
        assert conj_trigger is False

    def test_get_error_patterns(self):
        """Test getting all error patterns."""
        tracker = ErrorTracker()

        tracker.record_error("gender_agreement", "articles_1")
        tracker.record_error("verb_conjugation", "verbs_1")

        patterns = tracker.get_error_patterns()

        assert len(patterns) == 2

    def test_get_triggered_patterns(self):
        """Test getting only triggered patterns."""
        tracker = ErrorTracker()

        # Trigger one pattern
        for _ in range(3):
            tracker.record_error("gender_agreement", "articles_1")

        # Don't trigger another
        tracker.record_error("verb_conjugation", "verbs_1")

        triggered = tracker.get_triggered_patterns()

        assert len(triggered) == 1
        assert triggered[0].error_type == "gender_agreement"

    def test_get_pattern(self):
        """Test getting a specific pattern."""
        tracker = ErrorTracker()

        tracker.record_error("gender_agreement", "articles_1")

        pattern = tracker.get_pattern("gender_agreement", "articles_1")
        assert pattern is not None
        assert pattern.count == 1

        missing = tracker.get_pattern("missing", "missing")
        assert missing is None

    def test_reset_pattern(self):
        """Test resetting a pattern's trigger status."""
        tracker = ErrorTracker()

        # Trigger the pattern
        for _ in range(3):
            tracker.record_error("gender_agreement", "articles_1")

        pattern = tracker.get_pattern("gender_agreement", "articles_1")
        assert pattern.triggered is True

        # Reset it
        tracker.reset_pattern("gender_agreement", "articles_1")

        assert pattern.triggered is False

        # Should trigger again on 3 more errors
        for _ in range(3):
            tracker.record_error("gender_agreement", "articles_1")

        assert pattern.triggered is True

    def test_clear(self):
        """Test clearing all patterns."""
        tracker = ErrorTracker()

        tracker.record_error("gender_agreement", "articles_1")
        tracker.record_error("verb_conjugation", "verbs_1")

        tracker.clear()

        assert len(tracker.get_error_patterns()) == 0

    def test_serialization_roundtrip(self):
        """Test to_dict and from_dict preserve state."""
        tracker = ErrorTracker()

        for _ in range(3):
            tracker.record_error(
                "gender_agreement",
                "articles_1",
                student_response="el",
                expected_response="la",
            )

        data = tracker.to_dict()
        restored = ErrorTracker.from_dict(data)

        patterns = restored.get_error_patterns()
        assert len(patterns) == 1
        assert patterns[0].triggered is True
        assert patterns[0].count == 3

    def test_records_response_details(self):
        """Test that response details are recorded."""
        tracker = ErrorTracker()

        tracker.record_error(
            error_type="gender_agreement",
            concept_id="articles_1",
            student_response="el agua",
            expected_response="la agua",
        )

        pattern = tracker.get_pattern("gender_agreement", "articles_1")
        assert pattern.occurrences[0].student_response == "el agua"
        assert pattern.occurrences[0].expected_response == "la agua"
