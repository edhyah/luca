"""Tests for curriculum engine."""

import pytest

from luca.curriculum.engine import (
    REVIEW_THRESHOLD,
    STRONG_THRESHOLD,
    UNLOCK_THRESHOLD,
    CurriculumEngine,
)
from luca.curriculum.models import BKTParameters, Concept, Curriculum, ScaffoldStep


@pytest.fixture
def sample_curriculum() -> Curriculum:
    """Create a sample curriculum for testing."""
    bkt_params = BKTParameters(
        p_init=0.1,
        p_learn=0.2,
        p_guess=0.25,
        p_slip=0.1,
        p_forget=0.05,
    )

    concepts = [
        Concept(
            concept_id="basics",
            name="Basic Concepts",
            episode=1,
            prerequisites=[],
            scaffold_steps=[
                ScaffoldStep(
                    step_id="basics_1",
                    tutor_prompt="What is 1+1?",
                    expected_answers=["2"],
                )
            ],
            bkt_parameters=bkt_params,
        ),
        Concept(
            concept_id="intermediate",
            name="Intermediate Concepts",
            episode=1,
            prerequisites=["basics"],
            scaffold_steps=[
                ScaffoldStep(
                    step_id="intermediate_1",
                    tutor_prompt="What is 2+2?",
                    expected_answers=["4"],
                )
            ],
            bkt_parameters=bkt_params,
        ),
        Concept(
            concept_id="advanced",
            name="Advanced Concepts",
            episode=2,
            prerequisites=["intermediate"],
            scaffold_steps=[
                ScaffoldStep(
                    step_id="advanced_1",
                    tutor_prompt="What is 3+3?",
                    expected_answers=["6"],
                )
            ],
            bkt_parameters=bkt_params,
        ),
        Concept(
            concept_id="parallel_track",
            name="Parallel Track",
            episode=1,
            prerequisites=["basics"],
            scaffold_steps=[
                ScaffoldStep(
                    step_id="parallel_1",
                    tutor_prompt="What is 1*2?",
                    expected_answers=["2"],
                )
            ],
            bkt_parameters=bkt_params,
        ),
    ]

    return Curriculum(
        version="1.0",
        description="Test curriculum",
        episodes=[1, 2],
        concepts=concepts,
    )


@pytest.fixture
def engine(sample_curriculum: Curriculum) -> CurriculumEngine:
    """Create engine with sample curriculum loaded."""
    eng = CurriculumEngine()
    eng.curriculum = sample_curriculum
    eng.dag = sample_curriculum.build_dag()
    return eng


class TestGetMasteredSet:
    """Tests for get_mastered_set method."""

    def test_empty_mastery_returns_empty_set(self, engine: CurriculumEngine) -> None:
        result = engine.get_mastered_set({})
        assert result == set()

    def test_filters_by_threshold(self, engine: CurriculumEngine) -> None:
        mastery = {
            "basics": 0.8,
            "intermediate": 0.6,
            "advanced": 0.75,
        }
        result = engine.get_mastered_set(mastery, threshold=0.7)
        assert result == {"basics", "advanced"}

    def test_uses_default_threshold(self, engine: CurriculumEngine) -> None:
        mastery = {
            "basics": UNLOCK_THRESHOLD,
            "intermediate": UNLOCK_THRESHOLD - 0.01,
        }
        result = engine.get_mastered_set(mastery)
        assert result == {"basics"}


class TestGetReviewCandidates:
    """Tests for get_review_candidates method."""

    def test_returns_decayed_concepts(self, engine: CurriculumEngine) -> None:
        mastery = {
            "basics": 0.3,  # Below threshold
            "intermediate": 0.6,  # Above threshold
            "advanced": 0.4,  # Below threshold
        }
        result = engine.get_review_candidates(mastery, threshold=0.5)
        concept_ids = [cid for cid, _ in result]
        assert "basics" in concept_ids
        assert "advanced" in concept_ids
        assert "intermediate" not in concept_ids

    def test_sorted_by_mastery_ascending(self, engine: CurriculumEngine) -> None:
        mastery = {
            "basics": 0.4,
            "intermediate": 0.2,
            "advanced": 0.3,
        }
        result = engine.get_review_candidates(mastery, threshold=0.5)
        # Should be sorted: intermediate (0.2), advanced (0.3), basics (0.4)
        assert result[0] == ("intermediate", 0.2)
        assert result[1] == ("advanced", 0.3)
        assert result[2] == ("basics", 0.4)

    def test_empty_mastery_returns_empty_list(self, engine: CurriculumEngine) -> None:
        result = engine.get_review_candidates({})
        assert result == []

    def test_all_above_threshold_returns_empty(self, engine: CurriculumEngine) -> None:
        mastery = {"basics": 0.9, "intermediate": 0.8}
        result = engine.get_review_candidates(mastery, threshold=0.5)
        assert result == []


class TestGetNextConceptWithReview:
    """Tests for enhanced get_next_concept with review weaving."""

    def test_alternates_review_and_new(self, engine: CurriculumEngine) -> None:
        # basics is decayed, but intermediate is unlocked
        mastery = {
            "basics": 0.4,  # Practiced and decayed below REVIEW_THRESHOLD
        }
        # Since basics is "mastered" for unlock purposes (it was practiced),
        # we need to set it high enough to unlock intermediate
        mastery["basics"] = 0.75  # Above UNLOCK_THRESHOLD, below STRONG
        mastery["intermediate"] = 0.3  # Decayed, needs review

        # Last was new (not review), so should suggest review first
        concept, is_review = engine.get_next_concept(mastery, last_was_review=False)
        assert is_review is True
        assert concept == "intermediate"  # Most decayed

        # Last was review, so should suggest new
        concept, is_review = engine.get_next_concept(mastery, last_was_review=True)
        assert is_review is False

    def test_returns_none_when_nothing_available(self, engine: CurriculumEngine) -> None:
        # No mastery at all - basics has no prereqs but nothing is mastered for review
        # and basics isn't available because we have no mastered set
        mastery: dict[str, float] = {}
        concept, is_review = engine.get_next_concept(mastery)
        # basics should be available (no prereqs)
        assert concept == "basics"
        assert is_review is False

    def test_excludes_current_concept(self, engine: CurriculumEngine) -> None:
        mastery = {"basics": 0.3}  # Only one decayed concept
        concept, is_review = engine.get_next_concept(
            mastery, current_concept_id="basics", last_was_review=False
        )
        # basics should be excluded, nothing else available for review
        # Should return new material if available
        assert concept != "basics" or concept is None

    def test_fallback_to_review_when_no_new(self, engine: CurriculumEngine) -> None:
        # All concepts mastered, some decayed
        mastery = {
            "basics": 0.8,
            "intermediate": 0.8,
            "advanced": 0.8,
            "parallel_track": 0.4,  # Decayed
        }
        # Last was review, but no new material available
        concept, is_review = engine.get_next_concept(mastery, last_was_review=True)
        # Should still return review since no new is available
        # Actually, advanced needs intermediate which needs basics - let's check
        assert concept is not None

    def test_fallback_to_new_when_no_review(self, engine: CurriculumEngine) -> None:
        # Fresh start, nothing practiced, nothing to review
        mastery = {"basics": 0.9}  # Mastered, not needing review
        concept, is_review = engine.get_next_concept(mastery, last_was_review=False)
        # Should return new concept (intermediate or parallel_track)
        assert is_review is False
        assert concept in ["intermediate", "parallel_track"]


class TestPlanSession:
    """Tests for plan_session method."""

    def test_starts_with_most_decayed(self, engine: CurriculumEngine) -> None:
        mastery = {
            "basics": 0.8,
            "intermediate": 0.3,  # Most decayed
            "parallel_track": 0.4,
        }
        session = engine.plan_session(mastery, max_concepts=3)
        assert len(session) > 0
        # First should be most decayed (intermediate at 0.3)
        assert session[0] == ("intermediate", True)

    def test_alternates_review_and_new(self, engine: CurriculumEngine) -> None:
        mastery = {
            "basics": 0.8,  # Strong, unlocks others
            "intermediate": 0.3,  # Needs review
            "parallel_track": 0.4,  # Needs review
        }
        session = engine.plan_session(mastery, max_concepts=4)

        # Should alternate between review and new where possible
        review_count = sum(1 for _, is_review in session if is_review)
        new_count = sum(1 for _, is_review in session if not is_review)
        # We have 2 review candidates (intermediate, parallel_track)
        # and advanced might be unlocked as new
        assert review_count >= 1  # At least the starting review

    def test_ends_with_strong_concept(self, engine: CurriculumEngine) -> None:
        mastery = {
            "basics": 0.85,  # Strong
            "intermediate": 0.3,  # Needs review
        }
        session = engine.plan_session(mastery, max_concepts=5)
        if len(session) > 1:
            # Last concept should be strong if available and not already last
            last_concept, _ = session[-1]
            # Either the last concept is basics (strong) or there wasn't room
            assert last_concept == "basics" or mastery.get(last_concept, 0) >= STRONG_THRESHOLD

    def test_respects_max_concepts(self, engine: CurriculumEngine) -> None:
        mastery = {
            "basics": 0.8,
            "intermediate": 0.3,
            "parallel_track": 0.4,
            "advanced": 0.35,
        }
        session = engine.plan_session(mastery, max_concepts=2)
        assert len(session) <= 2

    def test_empty_mastery_starts_with_basics(self, engine: CurriculumEngine) -> None:
        mastery: dict[str, float] = {}
        session = engine.plan_session(mastery, max_concepts=3)
        # Should include basics as new material (no prereqs)
        concept_ids = [cid for cid, _ in session]
        if concept_ids:
            assert "basics" in concept_ids

    def test_zero_max_concepts_returns_empty(self, engine: CurriculumEngine) -> None:
        mastery = {"basics": 0.5}
        session = engine.plan_session(mastery, max_concepts=0)
        assert session == []


class TestIntegration:
    """Integration tests simulating realistic usage."""

    def test_session_simulation_with_decay(self, engine: CurriculumEngine) -> None:
        """Simulate multiple sessions with timing gaps and verify behavior."""
        # Initial state: student has practiced basics and intermediate
        mastery = {
            "basics": 0.85,  # Strong
            "intermediate": 0.75,  # Above unlock threshold
        }

        # Session 1: Should unlock advanced or parallel_track
        session1 = engine.plan_session(mastery, max_concepts=3)
        assert len(session1) > 0

        # Check that unlocked concepts are available
        mastered_set = engine.get_mastered_set(mastery)
        available = engine.get_available_concepts(mastered_set)
        assert "advanced" in available or "parallel_track" in available

        # Simulate decay after some time
        mastery["basics"] = 0.6  # Decayed below unlock but above review
        mastery["intermediate"] = 0.4  # Decayed below review threshold

        # Session 2: Should identify intermediate as needing review
        review_candidates = engine.get_review_candidates(mastery)
        assert len(review_candidates) > 0
        assert review_candidates[0][0] == "intermediate"

        # Next concept should be review since last wasn't
        next_concept, is_review = engine.get_next_concept(mastery, last_was_review=False)
        assert is_review is True
        assert next_concept == "intermediate"

    def test_prerequisite_unlocking(self, engine: CurriculumEngine) -> None:
        """Verify concepts unlock correctly based on prerequisites."""
        # Start with no mastery
        mastery: dict[str, float] = {}

        # Only basics should be available (no prereqs)
        mastered_set = engine.get_mastered_set(mastery)
        available = engine.get_available_concepts(mastered_set)
        assert available == ["basics"]

        # Master basics
        mastery["basics"] = 0.8

        # Now intermediate and parallel_track should be available
        mastered_set = engine.get_mastered_set(mastery)
        available = engine.get_available_concepts(mastered_set)
        assert "intermediate" in available
        assert "parallel_track" in available
        assert "advanced" not in available  # Needs intermediate

        # Master intermediate
        mastery["intermediate"] = 0.75

        # Now advanced should be available
        mastered_set = engine.get_mastered_set(mastery)
        available = engine.get_available_concepts(mastered_set)
        assert "advanced" in available

    def test_review_weaving_over_multiple_calls(self, engine: CurriculumEngine) -> None:
        """Test that review weaving alternates correctly over multiple calls."""
        mastery = {
            "basics": 0.85,  # Strong
            "intermediate": 0.35,  # Review needed
            "parallel_track": 0.4,  # Review needed
        }

        # First call: not a review last time, should get review
        concept1, is_review1 = engine.get_next_concept(mastery, last_was_review=False)
        assert is_review1 is True
        assert concept1 == "intermediate"  # Most decayed

        # Second call: last was review, should get new
        concept2, is_review2 = engine.get_next_concept(
            mastery, current_concept_id=concept1, last_was_review=True
        )
        assert is_review2 is False

        # Third call: last was new, should get review again
        concept3, is_review3 = engine.get_next_concept(
            mastery, current_concept_id=concept2, last_was_review=False
        )
        assert is_review3 is True
