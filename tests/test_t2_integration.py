"""Integration tests for T2: Data Model and Persistence Layer.

Demonstrates the complete round-trip:
1. Load curriculum from data/curriculum.json
2. Create session state for new student
3. Traverse DAG (get first available concept)
4. Get scaffold step, simulate response
5. Update mastery via BKT
6. Track sliding window stats
7. Advance through steps/concepts
"""

import pytest
from pathlib import Path

from luca.curriculum.engine import CurriculumEngine
from luca.curriculum.loader import CurriculumLoader
from luca.curriculum.models import (
    BKTParameters,
    CommonError,
    Concept,
    Curriculum,
    Revelation,
    ScaffoldStep,
)
from luca.student.session_state import SessionState, SlidingWindowStats


class TestPydanticModels:
    """Tests for the Pydantic curriculum models."""

    def test_bkt_parameters_validation(self):
        """Test BKT parameter constraints."""
        params = BKTParameters(
            p_init=0.1,
            p_learn=0.3,
            p_guess=0.2,
            p_slip=0.1,
            p_forget=0.05,
        )
        assert params.p_init == 0.1
        assert params.p_forget == 0.05

    def test_bkt_parameters_default_forget(self):
        """Test p_forget defaults to 0."""
        params = BKTParameters(
            p_init=0.1,
            p_learn=0.3,
            p_guess=0.2,
            p_slip=0.1,
        )
        assert params.p_forget == 0.0

    def test_bkt_parameters_bounds(self):
        """Test that parameters must be between 0 and 1."""
        with pytest.raises(ValueError):
            BKTParameters(
                p_init=1.5,  # Invalid: > 1
                p_learn=0.3,
                p_guess=0.2,
                p_slip=0.1,
            )

    def test_scaffold_step_creation(self):
        """Test scaffold step model."""
        step = ScaffoldStep(
            step_id="test_01",
            tutor_prompt="How do you say 'hello'?",
            expected_answers=["hola"],
            difficulty=2,
            hints=["Think of a common greeting"],
        )
        assert step.step_id == "test_01"
        assert step.revelation is None
        assert len(step.hints) == 1

    def test_scaffold_step_with_revelation(self):
        """Test scaffold step with revelation."""
        rev = Revelation(
            pattern_name="test_pattern",
            first_encounter_script="This is the pattern!",
            review_reference="Remember the pattern?",
        )
        step = ScaffoldStep(
            step_id="test_02",
            tutor_prompt="Test prompt",
            expected_answers=["answer"],
            revelation=rev,
        )
        assert step.revelation is not None
        assert step.revelation.pattern_name == "test_pattern"

    def test_concept_creation(self):
        """Test concept model creation."""
        concept = Concept(
            concept_id="test_concept",
            name="Test Concept",
            episode=1,
            prerequisites=["prereq_1"],
            scaffold_steps=[
                ScaffoldStep(
                    step_id="s1",
                    tutor_prompt="Step 1",
                    expected_answers=["answer"],
                )
            ],
            common_errors=[],
            bkt_parameters=BKTParameters(
                p_init=0.1,
                p_learn=0.3,
                p_guess=0.2,
                p_slip=0.1,
            ),
        )
        assert concept.concept_id == "test_concept"
        assert len(concept.prerequisites) == 1
        assert len(concept.scaffold_steps) == 1

    def test_curriculum_helper_methods(self):
        """Test curriculum helper methods."""
        curriculum = Curriculum(
            version="1.0.0",
            description="Test curriculum",
            episodes=[1, 2],
            concepts=[
                Concept(
                    concept_id="c1",
                    name="Concept 1",
                    episode=1,
                    prerequisites=[],
                    scaffold_steps=[],
                    common_errors=[],
                    bkt_parameters=BKTParameters(
                        p_init=0.1,
                        p_learn=0.2,
                        p_guess=0.2,
                        p_slip=0.1,
                    ),
                ),
                Concept(
                    concept_id="c2",
                    name="Concept 2",
                    episode=2,
                    prerequisites=["c1"],
                    scaffold_steps=[],
                    common_errors=[],
                    bkt_parameters=BKTParameters(
                        p_init=0.1,
                        p_learn=0.2,
                        p_guess=0.2,
                        p_slip=0.1,
                    ),
                ),
            ],
        )

        assert curriculum.get_concept("c1") is not None
        assert curriculum.get_concept("c3") is None
        assert curriculum.get_concept_ids() == ["c1", "c2"]
        dag = curriculum.build_dag()
        assert dag["c1"] == []
        assert dag["c2"] == ["c1"]


class TestCurriculumLoader:
    """Tests for curriculum loading."""

    def test_load_curriculum_json(self):
        """Test loading curriculum from JSON file."""
        loader = CurriculumLoader()
        curriculum_path = Path("data/curriculum.json")

        if not curriculum_path.exists():
            pytest.skip("data/curriculum.json not found")

        curriculum = loader.load_curriculum(str(curriculum_path))

        assert curriculum.version == "1.0.0"
        assert len(curriculum.concepts) > 0
        assert "cognate_al" in curriculum.get_concept_ids()

    def test_load_curriculum_file_not_found(self):
        """Test error when curriculum file doesn't exist."""
        loader = CurriculumLoader()
        with pytest.raises(FileNotFoundError):
            loader.load_curriculum("nonexistent.json")


class TestCurriculumEngine:
    """Tests for curriculum engine with typed models."""

    @pytest.fixture
    def engine(self):
        """Create a curriculum engine with loaded curriculum."""
        engine = CurriculumEngine()
        curriculum_path = Path("data/curriculum.json")
        if curriculum_path.exists():
            engine.load_curriculum(str(curriculum_path))
        return engine

    def test_load_curriculum(self, engine):
        """Test loading curriculum into engine."""
        if engine.curriculum is None:
            pytest.skip("data/curriculum.json not found")

        assert engine.curriculum is not None
        assert len(engine.dag) > 0

    def test_get_concept_typed(self, engine):
        """Test getting typed concept."""
        if engine.curriculum is None:
            pytest.skip("data/curriculum.json not found")

        concept = engine.get_concept("cognate_al")
        assert concept is not None
        assert concept.name == "Latin Cognates: -al suffix"
        assert isinstance(concept.bkt_parameters, BKTParameters)

    def test_get_scaffold_step(self, engine):
        """Test getting scaffold step."""
        if engine.curriculum is None:
            pytest.skip("data/curriculum.json not found")

        step = engine.get_scaffold_step("cognate_al", 0)
        assert step is not None
        assert step.step_id == "cognate_al_01"
        assert "normal" in step.expected_answers

    def test_get_scaffold_step_out_of_bounds(self, engine):
        """Test getting invalid scaffold step."""
        if engine.curriculum is None:
            pytest.skip("data/curriculum.json not found")

        step = engine.get_scaffold_step("cognate_al", 100)
        assert step is None

    def test_get_available_concepts_no_prerequisites(self, engine):
        """Test getting available concepts with no mastery."""
        if engine.curriculum is None:
            pytest.skip("data/curriculum.json not found")

        available = engine.get_available_concepts(set())
        # Should include concepts with no prerequisites
        assert "cognate_al" in available
        assert "phonetic_vowels" in available
        # Should not include concepts with unmet prerequisites
        assert "verb_es" not in available

    def test_get_available_concepts_with_mastery(self, engine):
        """Test getting available concepts with some mastery."""
        if engine.curriculum is None:
            pytest.skip("data/curriculum.json not found")

        mastered = {"cognate_al"}
        available = engine.get_available_concepts(mastered)
        # verb_es requires only cognate_al
        assert "verb_es" in available


class TestSlidingWindowStats:
    """Tests for sliding window statistics."""

    def test_empty_window(self):
        """Test stats on empty window."""
        stats = SlidingWindowStats()
        assert stats.streak_length == 0
        assert stats.error_rate == 0.0
        assert stats.avg_response_time == 0.0

    def test_streak_calculation(self):
        """Test streak length calculation."""
        stats = SlidingWindowStats()
        stats.add_response(True, 1.0)
        stats.add_response(True, 1.0)
        stats.add_response(True, 1.0)
        assert stats.streak_length == 3

        # Break the streak
        stats.add_response(False, 1.0)
        assert stats.streak_length == 0

        # Start new streak
        stats.add_response(True, 1.0)
        stats.add_response(True, 1.0)
        assert stats.streak_length == 2

    def test_error_rate_calculation(self):
        """Test error rate calculation."""
        stats = SlidingWindowStats()
        stats.add_response(True, 1.0)
        stats.add_response(False, 1.0)
        stats.add_response(True, 1.0)
        stats.add_response(False, 1.0)
        assert stats.error_rate == 0.5

    def test_avg_response_time(self):
        """Test average response time calculation."""
        stats = SlidingWindowStats()
        stats.add_response(True, 1.0)
        stats.add_response(True, 2.0)
        stats.add_response(True, 3.0)
        assert stats.avg_response_time == 2.0

    def test_window_size_limit(self):
        """Test that window respects size limit."""
        stats = SlidingWindowStats(window_size=3)
        for i in range(5):
            stats.add_response(True, float(i))

        assert stats.response_count == 3
        # Should have times 2.0, 3.0, 4.0 (last 3)
        assert stats.avg_response_time == 3.0


class TestSessionState:
    """Tests for session state tracking."""

    @pytest.fixture
    def curriculum(self):
        """Load curriculum for testing."""
        curriculum_path = Path("data/curriculum.json")
        if not curriculum_path.exists():
            pytest.skip("data/curriculum.json not found")

        loader = CurriculumLoader()
        return loader.load_curriculum(str(curriculum_path))

    def test_session_creation(self, curriculum):
        """Test creating a new session."""
        session = SessionState(student_id="test_student", curriculum=curriculum)
        assert session.student_id == "test_student"
        assert session.current_concept_id is None
        assert session.current_step_index == 0

    def test_bkt_initialization_from_curriculum(self, curriculum):
        """Test that BKT params are initialized from curriculum."""
        session = SessionState(student_id="test_student", curriculum=curriculum)

        # Check that params were set for a concept
        params = session.bkt.get_params("cognate_al")
        assert params["p_init"] == 0.0  # From curriculum
        assert params["p_learn"] == 0.35  # From curriculum

    def test_advance_concept(self, curriculum):
        """Test advancing to a concept."""
        session = SessionState(student_id="test_student", curriculum=curriculum)
        session.advance_concept("cognate_al")

        assert session.current_concept_id == "cognate_al"
        assert session.current_step_index == 0

    def test_get_current_step(self, curriculum):
        """Test getting the current scaffold step."""
        session = SessionState(student_id="test_student", curriculum=curriculum)
        session.advance_concept("cognate_al")

        step = session.get_current_step()
        assert step is not None
        assert step.step_id == "cognate_al_01"

    def test_record_response(self, curriculum):
        """Test recording a response updates mastery."""
        session = SessionState(student_id="test_student", curriculum=curriculum)
        session.advance_concept("cognate_al")

        initial_mastery = session.get_mastery("cognate_al")
        new_mastery = session.record_response(correct=True, response_time=2.0)

        assert new_mastery is not None
        assert new_mastery > initial_mastery

    def test_advance_step(self, curriculum):
        """Test advancing through scaffold steps."""
        session = SessionState(student_id="test_student", curriculum=curriculum)
        session.advance_concept("cognate_al")

        assert session.current_step_index == 0
        advanced = session.advance_step()
        assert advanced is True
        assert session.current_step_index == 1

    def test_advance_step_at_end(self, curriculum):
        """Test advance_step returns False at end of concept."""
        session = SessionState(student_id="test_student", curriculum=curriculum)
        session.advance_concept("cognate_al")

        # Advance to last step
        concept = curriculum.get_concept("cognate_al")
        for _ in range(len(concept.scaffold_steps) - 1):
            session.advance_step()

        # Should not advance past the last step
        advanced = session.advance_step()
        assert advanced is False

    def test_sliding_window_integration(self, curriculum):
        """Test sliding window stats are updated on responses."""
        session = SessionState(student_id="test_student", curriculum=curriculum)
        session.advance_concept("cognate_al")

        session.record_response(correct=True, response_time=1.5)
        session.record_response(correct=True, response_time=2.0)
        session.record_response(correct=False, response_time=3.0)

        assert session.get_streak() == 0  # Last was incorrect
        assert session.get_error_rate() == pytest.approx(1 / 3)

    def test_teaching_briefs(self, curriculum):
        """Test adding teaching briefs."""
        session = SessionState(student_id="test_student", curriculum=curriculum)
        session.add_teaching_brief("Student prefers visual examples")
        session.add_teaching_brief("Responds well to encouragement")
        session.add_teaching_brief("Student prefers visual examples")  # Duplicate

        assert len(session.teaching_briefs) == 2

    def test_is_concept_complete(self, curriculum):
        """Test checking if concept scaffold is complete."""
        session = SessionState(student_id="test_student", curriculum=curriculum)
        session.advance_concept("cognate_al")

        assert session.is_concept_complete() is False

        concept = curriculum.get_concept("cognate_al")
        for _ in range(len(concept.scaffold_steps) - 1):
            session.advance_step()

        assert session.is_concept_complete() is True


class TestFullIntegration:
    """Full integration test demonstrating the complete round-trip."""

    def test_complete_session_flow(self):
        """Test a complete session flow with curriculum traversal."""
        curriculum_path = Path("data/curriculum.json")
        if not curriculum_path.exists():
            pytest.skip("data/curriculum.json not found")

        # 1. Load curriculum
        engine = CurriculumEngine()
        curriculum = engine.load_curriculum(str(curriculum_path))
        assert curriculum is not None

        # 2. Create session state for new student
        session = SessionState(
            student_id="integration_test_student",
            curriculum=curriculum,
        )

        # 3. Get first available concept (no prerequisites mastered)
        available = engine.get_available_concepts(set())
        assert len(available) > 0
        first_concept_id = available[0]

        # 4. Start the concept
        session.advance_concept(first_concept_id)
        assert session.current_concept_id == first_concept_id

        # 5. Get scaffold step
        step = session.get_current_step()
        assert step is not None

        # 6. Simulate responses and update mastery
        initial_mastery = session.get_mastery(first_concept_id)

        # Simulate correct response
        new_mastery = session.record_response(correct=True, response_time=2.5)
        assert new_mastery > initial_mastery

        # 7. Track sliding window stats
        assert session.get_streak() == 1
        assert session.get_error_rate() == 0.0

        # Advance through steps
        concept = curriculum.get_concept(first_concept_id)
        for i in range(len(concept.scaffold_steps) - 1):
            session.advance_step()
            session.record_response(correct=True, response_time=1.5)

        # 8. Verify final state
        final_mastery = session.get_mastery(first_concept_id)
        assert final_mastery > initial_mastery
        assert session.is_concept_complete()

        # Verify streak is maintained
        total_responses = len(concept.scaffold_steps)
        assert session.get_streak() == total_responses
        assert session.get_error_rate() == 0.0

        # 9. Check that mastering first concept unlocks new ones
        mastered = {first_concept_id}
        new_available = engine.get_available_concepts(mastered)
        # Some concepts require the first concept as prerequisite
        # so new_available should have different concepts
        assert first_concept_id not in new_available
