"""Tests for trigger detection functionality."""

import pytest

from luca.student.triggers import TriggerDetector, TriggerEvent, TriggerType


class TestTriggerType:
    """Tests for TriggerType enum."""

    def test_enum_values(self):
        """Test that enum values are as expected."""
        assert TriggerType.ERROR_PATTERN.value == "error_pattern"
        assert TriggerType.MASTERY_THRESHOLD.value == "mastery_threshold"
        assert TriggerType.RESPONSE_SPEED_CHANGE.value == "response_speed_change"
        assert TriggerType.CONCEPT_TRANSITION.value == "concept_transition"


class TestTriggerEvent:
    """Tests for TriggerEvent dataclass."""

    def test_serialization_roundtrip(self):
        """Test to_dict and from_dict preserve data."""
        event = TriggerEvent(
            trigger_type=TriggerType.MASTERY_THRESHOLD,
            concept_id="articles_1",
            details={"direction": "up", "threshold": 0.7},
        )

        data = event.to_dict()
        restored = TriggerEvent.from_dict(data)

        assert restored.trigger_type == TriggerType.MASTERY_THRESHOLD
        assert restored.concept_id == "articles_1"
        assert restored.details["direction"] == "up"


class TestMasteryThresholdTrigger:
    """Tests for mastery threshold trigger detection."""

    def test_crossing_07_upward(self):
        """Test trigger fires when crossing 0.7 upward."""
        detector = TriggerDetector()

        event = detector.check_mastery_threshold(
            concept_id="articles_1",
            old_mastery=0.65,
            new_mastery=0.75,
        )

        assert event is not None
        assert event.trigger_type == TriggerType.MASTERY_THRESHOLD
        assert event.details["direction"] == "up"
        assert event.details["threshold"] == 0.7

    def test_crossing_07_downward(self):
        """Test trigger fires when crossing 0.7 downward."""
        detector = TriggerDetector()

        event = detector.check_mastery_threshold(
            concept_id="articles_1",
            old_mastery=0.75,
            new_mastery=0.65,
        )

        assert event is not None
        assert event.trigger_type == TriggerType.MASTERY_THRESHOLD
        assert event.details["direction"] == "down"
        assert event.details["threshold"] == 0.7

    def test_crossing_03_downward(self):
        """Test trigger fires when crossing 0.3 downward."""
        detector = TriggerDetector()

        event = detector.check_mastery_threshold(
            concept_id="articles_1",
            old_mastery=0.35,
            new_mastery=0.25,
        )

        assert event is not None
        assert event.trigger_type == TriggerType.MASTERY_THRESHOLD
        assert event.details["direction"] == "down"
        assert event.details["threshold"] == 0.3

    def test_no_trigger_below_threshold(self):
        """Test no trigger when staying below threshold."""
        detector = TriggerDetector()

        event = detector.check_mastery_threshold(
            concept_id="articles_1",
            old_mastery=0.50,
            new_mastery=0.55,
        )

        assert event is None

    def test_no_trigger_above_threshold(self):
        """Test no trigger when staying above threshold."""
        detector = TriggerDetector()

        event = detector.check_mastery_threshold(
            concept_id="articles_1",
            old_mastery=0.75,
            new_mastery=0.80,
        )

        assert event is None

    def test_crossing_exactly_at_threshold(self):
        """Test trigger fires when landing exactly on threshold."""
        detector = TriggerDetector()

        event = detector.check_mastery_threshold(
            concept_id="articles_1",
            old_mastery=0.65,
            new_mastery=0.70,
        )

        assert event is not None
        assert event.details["direction"] == "up"


class TestResponseSpeedTrigger:
    """Tests for response speed change trigger detection."""

    def test_50_percent_slower(self):
        """Test trigger fires when 50% slower."""
        detector = TriggerDetector()

        event = detector.check_response_speed(
            concept_id="articles_1",
            old_avg_time=2.0,
            new_avg_time=3.0,
        )

        assert event is not None
        assert event.trigger_type == TriggerType.RESPONSE_SPEED_CHANGE
        assert event.details["direction"] == "slower"
        assert event.details["change_ratio"] == 0.5

    def test_50_percent_faster(self):
        """Test trigger fires when 50% faster."""
        detector = TriggerDetector()

        event = detector.check_response_speed(
            concept_id="articles_1",
            old_avg_time=4.0,
            new_avg_time=2.0,
        )

        assert event is not None
        assert event.trigger_type == TriggerType.RESPONSE_SPEED_CHANGE
        assert event.details["direction"] == "faster"
        assert event.details["change_ratio"] == 0.5

    def test_no_trigger_small_change(self):
        """Test no trigger for small speed changes."""
        detector = TriggerDetector()

        event = detector.check_response_speed(
            concept_id="articles_1",
            old_avg_time=2.0,
            new_avg_time=2.5,  # 25% change
        )

        assert event is None

    def test_no_trigger_zero_old_time(self):
        """Test no trigger when old_avg_time is 0."""
        detector = TriggerDetector()

        event = detector.check_response_speed(
            concept_id="articles_1",
            old_avg_time=0,
            new_avg_time=2.0,
        )

        assert event is None


class TestConceptTransitionTrigger:
    """Tests for concept transition trigger detection."""

    def test_first_concept_triggers(self):
        """Test trigger fires for first concept visited."""
        detector = TriggerDetector()

        event = detector.check_concept_transition(
            old_concept_id=None,
            new_concept_id="articles_1",
        )

        assert event is not None
        assert event.trigger_type == TriggerType.CONCEPT_TRANSITION
        assert event.concept_id == "articles_1"
        assert event.details["from_concept"] is None
        assert event.details["to_concept"] == "articles_1"

    def test_new_concept_triggers(self):
        """Test trigger fires when moving to new concept."""
        detector = TriggerDetector()

        # Visit first concept
        detector.check_concept_transition(None, "articles_1")

        # Move to new concept
        event = detector.check_concept_transition(
            old_concept_id="articles_1",
            new_concept_id="verbs_1",
        )

        assert event is not None
        assert event.concept_id == "verbs_1"

    def test_revisiting_concept_no_trigger(self):
        """Test no trigger when revisiting a concept."""
        detector = TriggerDetector()

        # Visit concept
        detector.check_concept_transition(None, "articles_1")

        # Revisit same concept
        event = detector.check_concept_transition(
            old_concept_id="verbs_1",
            new_concept_id="articles_1",
        )

        assert event is None

    def test_mark_concept_visited(self):
        """Test marking concept as visited prevents trigger."""
        detector = TriggerDetector()

        # Mark as already visited
        detector.mark_concept_visited("articles_1")

        # Should not trigger
        event = detector.check_concept_transition(None, "articles_1")

        assert event is None


class TestTriggerDetectorState:
    """Tests for TriggerDetector state management."""

    def test_update_and_get_prev_mastery(self):
        """Test tracking previous mastery levels."""
        detector = TriggerDetector()

        detector.update_prev_mastery("articles_1", 0.5)
        assert detector.get_prev_mastery("articles_1") == 0.5

        assert detector.get_prev_mastery("unknown") is None

    def test_update_and_get_prev_response_time(self):
        """Test tracking previous response times."""
        detector = TriggerDetector()

        detector.update_prev_response_time("articles_1", 2.5)
        assert detector.get_prev_response_time("articles_1") == 2.5

        assert detector.get_prev_response_time("unknown") is None

    def test_serialization_roundtrip(self):
        """Test to_dict and from_dict preserve state."""
        detector = TriggerDetector()

        detector.update_prev_mastery("articles_1", 0.6)
        detector.update_prev_response_time("articles_1", 2.0)
        detector.mark_concept_visited("articles_1")
        detector.mark_concept_visited("verbs_1")

        data = detector.to_dict()
        restored = TriggerDetector.from_dict(data)

        assert restored.get_prev_mastery("articles_1") == 0.6
        assert restored.get_prev_response_time("articles_1") == 2.0

        # Should not trigger for visited concepts
        event = restored.check_concept_transition(None, "articles_1")
        assert event is None
