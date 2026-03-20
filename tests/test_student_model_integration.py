"""Integration tests for the full StudentModel."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from luca.curriculum.models import BKTParameters, Concept, Curriculum, ScaffoldStep
from luca.student.model import StudentModel
from luca.student.triggers import TriggerType


def make_curriculum() -> Curriculum:
    """Create a test curriculum."""
    return Curriculum(
        version="1.0",
        description="Test curriculum",
        episodes=[1],
        concepts=[
            Concept(
                concept_id="articles_1",
                name="Basic Articles",
                episode=1,
                prerequisites=[],
                scaffold_steps=[
                    ScaffoldStep(
                        step_id="step_1",
                        tutor_prompt="What is 'the water' in Spanish?",
                        expected_answers=["el agua"],
                    )
                ],
                common_errors=[],
                bkt_parameters=BKTParameters(
                    p_init=0.1,
                    p_learn=0.2,
                    p_guess=0.25,
                    p_slip=0.1,
                    p_forget=0.05,
                ),
            ),
            Concept(
                concept_id="articles_2",
                name="Advanced Articles",
                episode=1,
                prerequisites=["articles_1"],
                scaffold_steps=[],
                common_errors=[],
                bkt_parameters=BKTParameters(
                    p_init=0.1,
                    p_learn=0.15,
                    p_guess=0.2,
                    p_slip=0.1,
                    p_forget=0.03,
                ),
            ),
        ],
    )


class TestStudentModelInit:
    """Tests for StudentModel initialization."""

    def test_init_basic(self):
        """Test basic initialization."""
        model = StudentModel("student_1")

        assert model.student_id == "student_1"
        assert model.current_concept_id is None
        assert len(model.session_history) == 0
        assert len(model.teaching_briefs) == 0

    def test_init_with_curriculum(self):
        """Test initialization with curriculum."""
        curriculum = make_curriculum()
        model = StudentModel("student_1", curriculum=curriculum)

        # BKT params should be set from curriculum
        params = model.bkt.get_params("articles_1")
        assert params["p_init"] == 0.1
        assert params["p_learn"] == 0.2
        assert params["p_forget"] == 0.05


class TestRecordResponse:
    """Tests for recording responses."""

    def test_correct_response_increases_mastery(self):
        """Test that correct responses increase mastery."""
        model = StudentModel("student_1")

        initial = model.get_mastery("articles_1")
        model.record_response("articles_1", correct=True)
        updated = model.get_mastery("articles_1")

        assert updated > initial

    def test_incorrect_response_with_error_type(self):
        """Test recording incorrect response with error tracking."""
        model = StudentModel("student_1")

        triggers = model.record_response(
            "articles_1",
            correct=False,
            error_type="gender_agreement",
            student_response="el agua",
            expected_response="la agua",
        )

        # First error shouldn't trigger
        assert len(triggers) == 0

        # Pattern should be tracked
        pattern = model.error_tracker.get_pattern("gender_agreement", "articles_1")
        assert pattern is not None
        assert pattern.count == 1

    def test_third_error_triggers(self):
        """Test that third error triggers error pattern."""
        model = StudentModel("student_1")

        # Record 3 errors
        model.record_response("articles_1", correct=False, error_type="gender")
        model.record_response("articles_1", correct=False, error_type="gender")
        triggers = model.record_response("articles_1", correct=False, error_type="gender")

        # Should have error pattern trigger
        error_triggers = [t for t in triggers if t.trigger_type == TriggerType.ERROR_PATTERN]
        assert len(error_triggers) == 1
        assert error_triggers[0].details["error_type"] == "gender"

    def test_mastery_threshold_trigger(self):
        """Test mastery threshold triggers."""
        model = StudentModel("student_1")

        # Start below threshold
        model.bkt.set_mastery("articles_1", 0.68)

        # Update that crosses 0.7
        model.bkt.params["articles_1"] = {
            "p_init": 0.1, "p_learn": 0.3, "p_guess": 0.1, "p_slip": 0.05, "p_forget": 0.0
        }
        triggers = model.record_response("articles_1", correct=True)

        # Check if we crossed the threshold
        new_mastery = model.get_mastery("articles_1")
        if new_mastery >= 0.7:
            mastery_triggers = [t for t in triggers if t.trigger_type == TriggerType.MASTERY_THRESHOLD]
            assert len(mastery_triggers) == 1
            assert mastery_triggers[0].details["direction"] == "up"

    def test_session_history_recorded(self):
        """Test that responses are recorded to session history."""
        model = StudentModel("student_1")

        model.record_response("articles_1", correct=True, response_time=2.5)

        assert len(model.session_history) == 1
        entry = model.session_history[0]
        assert entry["concept_id"] == "articles_1"
        assert entry["correct"] is True
        assert entry["response_time"] == 2500  # milliseconds


class TestAdvanceConcept:
    """Tests for concept advancement."""

    def test_first_concept_triggers(self):
        """Test first concept triggers transition."""
        model = StudentModel("student_1")

        trigger = model.advance_concept("articles_1")

        assert trigger is not None
        assert trigger.trigger_type == TriggerType.CONCEPT_TRANSITION
        assert model.current_concept_id == "articles_1"

    def test_new_concept_triggers(self):
        """Test new concept triggers transition."""
        model = StudentModel("student_1")

        model.advance_concept("articles_1")
        trigger = model.advance_concept("articles_2")

        assert trigger is not None
        assert trigger.details["from_concept"] == "articles_1"
        assert trigger.details["to_concept"] == "articles_2"

    def test_revisit_no_trigger(self):
        """Test revisiting concept doesn't trigger."""
        model = StudentModel("student_1")

        model.advance_concept("articles_1")
        model.advance_concept("articles_2")
        trigger = model.advance_concept("articles_1")

        assert trigger is None


class TestGenerateBrief:
    """Tests for teaching brief generation."""

    @pytest.mark.asyncio
    async def test_generate_brief_mocked(self):
        """Test brief generation with mocked API."""
        model = StudentModel("student_1")

        # Add some history
        model.record_response("articles_1", correct=True)
        model.record_response("articles_1", correct=False, error_type="gender")

        # Mock the API call
        with patch("luca.student.teaching_brief.genai") as mock_genai:
            mock_response = MagicMock()
            mock_response.text = '''```json
{
    "strengths": ["Quick learner"],
    "challenges": ["Gender agreement"],
    "error_patterns": ["Confuses el/la"],
    "effective_strategies": ["Use mnemonics"],
    "preferred_explanation_style": "Visual",
    "summary": "Good progress but needs help with articles."
}
```'''
            mock_model = MagicMock()
            mock_model.generate_content_async = AsyncMock(return_value=mock_response)
            mock_genai.GenerativeModel.return_value = mock_model

            # Set API key env var
            with patch.dict("os.environ", {"GOOGLE_API_KEY": "test-key"}):
                from luca.student.triggers import TriggerEvent, TriggerType

                trigger = TriggerEvent(
                    trigger_type=TriggerType.ERROR_PATTERN,
                    concept_id="articles_1",
                )

                brief = await model.generate_brief_for_trigger(trigger)

        assert brief.student_id == "student_1"
        assert "Quick learner" in brief.strengths
        assert "Gender agreement" in brief.challenges
        assert len(model.teaching_briefs) == 1

    @pytest.mark.asyncio
    async def test_max_briefs_limit(self):
        """Test that only MAX_BRIEFS are kept."""
        model = StudentModel("student_1")

        with patch("luca.student.teaching_brief.genai") as mock_genai:
            mock_response = MagicMock()
            mock_response.text = '{"strengths": [], "challenges": [], "error_patterns": [], "effective_strategies": [], "preferred_explanation_style": "", "summary": "Test"}'
            mock_model = MagicMock()
            mock_model.generate_content_async = AsyncMock(return_value=mock_response)
            mock_genai.GenerativeModel.return_value = mock_model

            with patch.dict("os.environ", {"GOOGLE_API_KEY": "test-key"}):
                from luca.student.triggers import TriggerEvent, TriggerType

                # Generate more than MAX_BRIEFS
                for i in range(5):
                    trigger = TriggerEvent(
                        trigger_type=TriggerType.ERROR_PATTERN,
                        concept_id=f"concept_{i}",
                    )
                    await model.generate_brief_for_trigger(trigger)

        assert len(model.teaching_briefs) == StudentModel.MAX_BRIEFS


class TestGetters:
    """Tests for getter methods."""

    def test_get_mastery(self):
        """Test get_mastery returns correct value."""
        model = StudentModel("student_1")
        model.bkt.set_mastery("articles_1", 0.75)

        assert model.get_mastery("articles_1") == 0.75

    def test_get_all_mastery(self):
        """Test get_all_mastery returns all values."""
        model = StudentModel("student_1")
        model.bkt.set_mastery("articles_1", 0.75)
        model.bkt.set_mastery("articles_2", 0.50)

        all_mastery = model.get_all_mastery()

        assert all_mastery == {"articles_1": 0.75, "articles_2": 0.50}

    def test_get_ready_concepts(self):
        """Test get_ready_concepts returns mastered concepts."""
        model = StudentModel("student_1")
        model.bkt.set_mastery("articles_1", 0.85)
        model.bkt.set_mastery("articles_2", 0.50)

        ready = model.get_ready_concepts(threshold=0.8)

        assert "articles_1" in ready
        assert "articles_2" not in ready

    def test_get_latest_brief(self):
        """Test get_latest_brief returns most recent."""
        model = StudentModel("student_1")

        # No briefs yet
        assert model.get_latest_brief() is None

        # Add a brief
        from luca.student.teaching_brief import TeachingBrief
        model.teaching_briefs.append(TeachingBrief(student_id="student_1", summary="First"))
        model.teaching_briefs.append(TeachingBrief(student_id="student_1", summary="Second"))

        latest = model.get_latest_brief()
        assert latest.summary == "Second"

    def test_get_sliding_stats(self):
        """Test get_sliding_stats returns correct values."""
        model = StudentModel("student_1")

        model.sliding_window.add_response(True, 2.0)
        model.sliding_window.add_response(True, 3.0)
        model.sliding_window.add_response(False, 4.0)

        stats = model.get_sliding_stats()

        assert stats["response_count"] == 3
        assert stats["error_rate"] == pytest.approx(1/3)
        assert stats["avg_response_time"] == 3.0
        assert stats["streak_length"] == 0  # Last was incorrect


class TestIntegrationScenario:
    """Integration test simulating a real session."""

    def test_30_attempts_scenario(self):
        """Simulate 30 concept attempts with varying correctness."""
        curriculum = make_curriculum()
        model = StudentModel("student_1", curriculum=curriculum)

        all_triggers = []

        # Start with first concept
        trigger = model.advance_concept("articles_1")
        if trigger:
            all_triggers.append(trigger)

        # Simulate 30 attempts
        # Pattern: mostly correct with some errors
        responses = [
            True, True, False, True, True,  # 1-5
            True, False, True, True, True,  # 6-10
            True, True, True, False, True,  # 11-15
            True, True, True, True, False,  # 16-20
            False, False, True, True, True,  # 21-25 (error cluster)
            True, True, True, True, True,   # 26-30
        ]

        for i, correct in enumerate(responses):
            error_type = "gender_agreement" if not correct else None
            triggers = model.record_response(
                "articles_1",
                correct=correct,
                response_time=2.0 + (0.5 if not correct else 0),
                error_type=error_type,
            )
            all_triggers.extend(triggers)

        # Check final state
        final_mastery = model.get_mastery("articles_1")

        # With 24 correct and 6 incorrect, mastery should be high
        assert final_mastery > 0.7, f"Expected mastery > 0.7, got {final_mastery}"

        # Should have some triggers
        # - At least the concept transition
        # - Possibly mastery threshold crossings
        assert len(all_triggers) >= 1

        # Check session history
        assert len(model.session_history) == 30

        # Check error tracking
        pattern = model.error_tracker.get_pattern("gender_agreement", "articles_1")
        assert pattern is not None
        assert pattern.count == 6  # 6 incorrect responses

        # Error pattern should have triggered (3+ occurrences)
        error_triggers = [t for t in all_triggers if t.trigger_type == TriggerType.ERROR_PATTERN]
        assert len(error_triggers) >= 1

    def test_concept_transition_scenario(self):
        """Test transitioning between multiple concepts."""
        curriculum = make_curriculum()
        model = StudentModel("student_1", curriculum=curriculum)

        triggers = []

        # First concept
        t = model.advance_concept("articles_1")
        if t:
            triggers.append(t)

        # Build mastery
        for _ in range(5):
            model.record_response("articles_1", correct=True)

        # Second concept
        t = model.advance_concept("articles_2")
        if t:
            triggers.append(t)

        # Some work on second concept
        for _ in range(3):
            model.record_response("articles_2", correct=True)

        # Return to first concept (shouldn't trigger)
        t = model.advance_concept("articles_1")
        if t:
            triggers.append(t)

        # Should have 2 concept transition triggers
        transition_triggers = [t for t in triggers if t.trigger_type == TriggerType.CONCEPT_TRANSITION]
        assert len(transition_triggers) == 2

        # Check mastery for both concepts
        assert model.get_mastery("articles_1") > model.bkt.DEFAULT_PARAMS["p_init"]
        assert model.get_mastery("articles_2") > model.bkt.DEFAULT_PARAMS["p_init"]
