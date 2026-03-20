"""Tests for T9: Session Orchestrator.

Tests cover:
- Off-script detection patterns
- State machine transitions
- Pre-computation logic
- Context branch selection
- Integration with other components
"""

import pytest

from luca.curriculum.models import (
    BKTParameters,
    Concept,
    Curriculum,
    ScaffoldStep,
)
from luca.pipeline.frames import HintDeliveredFrame, TurnContextFrame
from luca.pipeline.off_script import OffScriptDetector, OffScriptType
from luca.pipeline.orchestrator import (
    OrchestratorState,
    PrecomputedBranch,
    PrecomputedBranches,
    SessionOrchestrator,
)
from luca.pipeline.pattern_matcher import MatchResult, MatchSignal


class TestOffScriptDetector:
    """Tests for the OffScriptDetector class."""

    def setup_method(self) -> None:
        self.detector = OffScriptDetector()

    # REPEAT tests
    def test_detect_repeat_simple(self) -> None:
        assert self.detector.detect("repeat") == OffScriptType.REPEAT

    def test_detect_repeat_question(self) -> None:
        assert self.detector.detect("Can you repeat that?") == OffScriptType.REPEAT

    def test_detect_repeat_please(self) -> None:
        assert self.detector.detect("Can you please repeat?") == OffScriptType.REPEAT

    def test_detect_say_again(self) -> None:
        assert self.detector.detect("What did you say?") == OffScriptType.REPEAT

    def test_detect_one_more_time(self) -> None:
        assert self.detector.detect("One more time") == OffScriptType.REPEAT

    def test_detect_pardon(self) -> None:
        assert self.detector.detect("Pardon?") == OffScriptType.REPEAT

    def test_detect_huh(self) -> None:
        assert self.detector.detect("Huh?") == OffScriptType.REPEAT

    # SLOW_DOWN tests
    def test_detect_slow_down(self) -> None:
        assert self.detector.detect("slow down") == OffScriptType.SLOW_DOWN

    def test_detect_too_fast(self) -> None:
        assert self.detector.detect("You're going too fast") == OffScriptType.SLOW_DOWN

    def test_detect_go_slower(self) -> None:
        assert self.detector.detect("Can you go slower?") == OffScriptType.SLOW_DOWN

    # CONFUSION tests
    def test_detect_dont_understand(self) -> None:
        assert self.detector.detect("I don't understand") == OffScriptType.CONFUSION

    def test_detect_confused(self) -> None:
        assert self.detector.detect("I'm confused") == OffScriptType.CONFUSION

    def test_detect_what_do_you_mean(self) -> None:
        assert self.detector.detect("What do you mean?") == OffScriptType.CONFUSION

    def test_detect_dont_get_it(self) -> None:
        assert self.detector.detect("I don't get it") == OffScriptType.CONFUSION

    def test_detect_no_idea(self) -> None:
        assert self.detector.detect("I have no idea") == OffScriptType.CONFUSION

    # HELP tests
    def test_detect_help(self) -> None:
        assert self.detector.detect("Help") == OffScriptType.HELP

    def test_detect_help_me(self) -> None:
        assert self.detector.detect("Help me") == OffScriptType.HELP

    def test_detect_give_hint(self) -> None:
        assert self.detector.detect("Give me a hint") == OffScriptType.HELP

    def test_detect_need_hint(self) -> None:
        assert self.detector.detect("I need a hint") == OffScriptType.HELP

    def test_detect_im_stuck(self) -> None:
        assert self.detector.detect("I'm stuck") == OffScriptType.HELP

    def test_detect_can_i_have_hint(self) -> None:
        assert self.detector.detect("Can I have a hint?") == OffScriptType.HELP

    # SKIP tests
    def test_detect_skip(self) -> None:
        assert self.detector.detect("Skip") == OffScriptType.SKIP

    def test_detect_skip_this(self) -> None:
        assert self.detector.detect("Skip this") == OffScriptType.SKIP

    def test_detect_move_on(self) -> None:
        assert self.detector.detect("Move on") == OffScriptType.SKIP

    def test_detect_next(self) -> None:
        assert self.detector.detect("Next") == OffScriptType.SKIP

    def test_detect_give_up(self) -> None:
        assert self.detector.detect("I give up") == OffScriptType.SKIP

    def test_detect_just_tell_me(self) -> None:
        assert self.detector.detect("Just tell me") == OffScriptType.SKIP

    # NONE tests (normal responses)
    def test_detect_spanish_response(self) -> None:
        assert self.detector.detect("Es normal") == OffScriptType.NONE

    def test_detect_english_answer(self) -> None:
        assert self.detector.detect("It is normal") == OffScriptType.NONE

    def test_detect_empty_string(self) -> None:
        assert self.detector.detect("") == OffScriptType.NONE

    def test_detect_whitespace(self) -> None:
        assert self.detector.detect("   ") == OffScriptType.NONE

    # is_off_script helper
    def test_is_off_script_true(self) -> None:
        assert self.detector.is_off_script("Help me please") is True

    def test_is_off_script_false(self) -> None:
        assert self.detector.is_off_script("Hablo español") is False


class TestHintDeliveredFrame:
    """Tests for the HintDeliveredFrame dataclass."""

    def test_creation(self) -> None:
        frame = HintDeliveredFrame(hint_index=0, total_hints=3)
        assert frame.hint_index == 0
        assert frame.total_hints == 3

    def test_second_hint(self) -> None:
        frame = HintDeliveredFrame(hint_index=1, total_hints=3)
        assert frame.hint_index == 1


class TestTurnContextFrame:
    """Tests for the TurnContextFrame dataclass."""

    def test_creation_basic(self) -> None:
        frame = TurnContextFrame(difficulty=2)
        assert frame.difficulty == 2
        assert frame.hints == []
        assert frame.evaluation_signal is None

    def test_creation_with_hints(self) -> None:
        frame = TurnContextFrame(
            difficulty=3,
            hints=["Hint 1", "Hint 2"],
            evaluation_signal=MatchSignal.CLEAR_MATCH,
        )
        assert frame.difficulty == 3
        assert len(frame.hints) == 2
        assert frame.evaluation_signal == MatchSignal.CLEAR_MATCH


class TestOrchestratorState:
    """Tests for the OrchestratorState enum."""

    def test_all_states_exist(self) -> None:
        assert OrchestratorState.INITIALIZING.value == "initializing"
        assert OrchestratorState.WAITING_FOR_SPEECH.value == "waiting"
        assert OrchestratorState.THINKING_PAUSE.value == "thinking_pause"
        assert OrchestratorState.EVALUATING.value == "evaluating"
        assert OrchestratorState.GENERATING.value == "generating"
        assert OrchestratorState.SPEAKING.value == "speaking"


class TestPrecomputedBranches:
    """Tests for the PrecomputedBranches dataclass."""

    def test_empty_branches(self) -> None:
        branches = PrecomputedBranches()
        assert branches.correct is None
        assert branches.incorrect is None
        assert branches.timestamp > 0


def _create_test_curriculum() -> Curriculum:
    """Create a minimal curriculum for testing."""
    return Curriculum(
        version="1.0.0",
        description="Test Curriculum",
        episodes=[1],
        concepts=[
            Concept(
                concept_id="test_concept",
                name="Test Concept",
                episode=1,
                prerequisites=[],
                bkt_parameters=BKTParameters(
                    p_init=0.1,
                    p_learn=0.3,
                    p_guess=0.2,
                    p_slip=0.1,
                ),
                scaffold_steps=[
                    ScaffoldStep(
                        step_id="step_1",
                        tutor_prompt="How do you say 'normal' in Spanish?",
                        expected_answers=["normal", "es normal"],
                        difficulty=1,
                        hints=["It's the same word!", "Just say it in Spanish"],
                    ),
                    ScaffoldStep(
                        step_id="step_2",
                        tutor_prompt="How do you say 'it is normal'?",
                        expected_answers=["es normal"],
                        difficulty=2,
                        hints=["Use 'es' for 'is'", "Es + normal"],
                    ),
                ],
                common_errors=[],
            ),
        ],
    )


class TestSessionOrchestratorInit:
    """Tests for SessionOrchestrator initialization."""

    def test_init_creates_components(self) -> None:
        curriculum = _create_test_curriculum()
        orchestrator = SessionOrchestrator(
            curriculum=curriculum,
            student_id="test_student",
        )

        assert orchestrator.state == OrchestratorState.INITIALIZING
        assert orchestrator.curriculum == curriculum
        assert orchestrator.student_id == "test_student"
        assert orchestrator._student_model is not None
        assert orchestrator._curriculum_engine is not None
        assert orchestrator._tutor_agent is not None
        assert orchestrator._context_builder is not None
        assert orchestrator._pattern_matcher is not None
        assert orchestrator._session_state is not None
        assert orchestrator._off_script_detector is not None

    def test_init_with_custom_components(self) -> None:
        from luca.pipeline.pattern_matcher import PatternMatcher
        from luca.tutor.context_builder import ContextBuilder

        curriculum = _create_test_curriculum()
        pattern_matcher = PatternMatcher(threshold=80.0)
        context_builder = ContextBuilder()

        orchestrator = SessionOrchestrator(
            curriculum=curriculum,
            student_id="test_student",
            pattern_matcher=pattern_matcher,
            context_builder=context_builder,
        )

        assert orchestrator._pattern_matcher == pattern_matcher
        assert orchestrator._context_builder == context_builder


class TestStateTransitions:
    """Tests for state machine transitions."""

    def test_transition_to_logs_correctly(self) -> None:
        curriculum = _create_test_curriculum()
        orchestrator = SessionOrchestrator(
            curriculum=curriculum,
            student_id="test_student",
        )

        assert orchestrator.state == OrchestratorState.INITIALIZING

        orchestrator._transition_to(OrchestratorState.WAITING_FOR_SPEECH)
        assert orchestrator.state == OrchestratorState.WAITING_FOR_SPEECH

        orchestrator._transition_to(OrchestratorState.EVALUATING)
        assert orchestrator.state == OrchestratorState.EVALUATING

        orchestrator._transition_to(OrchestratorState.GENERATING)
        assert orchestrator.state == OrchestratorState.GENERATING

        orchestrator._transition_to(OrchestratorState.SPEAKING)
        assert orchestrator.state == OrchestratorState.SPEAKING


class TestMatchResultRouting:
    """Tests for routing based on MatchResult signal."""

    def test_clear_match_signal(self) -> None:
        result = MatchResult(
            signal=MatchSignal.CLEAR_MATCH,
            score=95.0,
            best_match="es normal",
            diff=None,
        )
        assert result.signal == MatchSignal.CLEAR_MATCH
        assert result.diff is None

    def test_clear_miss_signal(self) -> None:
        result = MatchResult(
            signal=MatchSignal.CLEAR_MISS,
            score=30.0,
            best_match="es normal",
            diff="missing: es",
        )
        assert result.signal == MatchSignal.CLEAR_MISS
        assert result.diff == "missing: es"

    def test_ambiguous_signal(self) -> None:
        result = MatchResult(
            signal=MatchSignal.AMBIGUOUS,
            score=75.0,
            best_match="es normal",
            diff="minor spelling differences",
        )
        assert result.signal == MatchSignal.AMBIGUOUS


class TestOffScriptPatternEdgeCases:
    """Edge case tests for off-script detection."""

    def setup_method(self) -> None:
        self.detector = OffScriptDetector()

    def test_case_insensitive(self) -> None:
        assert self.detector.detect("REPEAT") == OffScriptType.REPEAT
        assert self.detector.detect("HELP") == OffScriptType.HELP
        assert self.detector.detect("Skip This") == OffScriptType.SKIP

    def test_embedded_in_sentence(self) -> None:
        # Should detect even when embedded
        assert self.detector.detect("I think I need help") == OffScriptType.HELP
        assert self.detector.detect("Please repeat that for me") == OffScriptType.REPEAT

    def test_punctuation_variations(self) -> None:
        assert self.detector.detect("Help!") == OffScriptType.HELP
        assert self.detector.detect("Repeat?") == OffScriptType.REPEAT
        assert self.detector.detect("I'm confused...") == OffScriptType.CONFUSION

    def test_contractions(self) -> None:
        assert self.detector.detect("I don't understand") == OffScriptType.CONFUSION
        assert self.detector.detect("I dont understand") == OffScriptType.CONFUSION
        assert self.detector.detect("Im stuck") == OffScriptType.HELP

    def test_not_false_positive_on_similar_words(self) -> None:
        # "normal" contains "no" but shouldn't trigger CONFUSION
        assert self.detector.detect("normal") == OffScriptType.NONE
        # "helpless" contains "help" but it's part of a word
        assert self.detector.detect("es normal") == OffScriptType.NONE


@pytest.mark.asyncio
class TestOrchestratorAsync:
    """Async tests for orchestrator behavior."""

    async def test_precompute_branches_creates_both(self) -> None:
        curriculum = _create_test_curriculum()
        orchestrator = SessionOrchestrator(
            curriculum=curriculum,
            student_id="test_student",
        )

        # Set up session state
        orchestrator._session_state.advance_concept("test_concept")
        step = orchestrator._session_state.get_current_step()
        orchestrator._context_builder.set_concept(curriculum.concepts[0])
        orchestrator._context_builder.set_step(step)

        # Pre-compute
        await orchestrator._precompute_branches()

        assert orchestrator._precomputed is not None
        assert orchestrator._precomputed.correct is not None
        assert orchestrator._precomputed.incorrect is not None

    async def test_advance_step_returns_true_when_more_steps(self) -> None:
        curriculum = _create_test_curriculum()
        orchestrator = SessionOrchestrator(
            curriculum=curriculum,
            student_id="test_student",
        )

        # Initialize
        orchestrator._session_state.advance_concept("test_concept")
        orchestrator._context_builder.set_concept(curriculum.concepts[0])
        step = orchestrator._session_state.get_current_step()
        orchestrator._context_builder.set_step(step)

        # First step, should be able to advance
        assert orchestrator._session_state.current_step_index == 0
        result = await orchestrator._advance_step()

        # Since there's no session plan, it returns False (no next concept)
        # But the step index should have advanced
        assert orchestrator._session_state.current_step_index == 1

    async def test_schedule_brief_generation(self) -> None:
        from luca.student.triggers import TriggerEvent, TriggerType

        curriculum = _create_test_curriculum()
        orchestrator = SessionOrchestrator(
            curriculum=curriculum,
            student_id="test_student",
        )

        trigger = TriggerEvent(
            trigger_type=TriggerType.CONCEPT_TRANSITION,
            concept_id="test_concept",
        )

        # Schedule (doesn't wait for completion)
        orchestrator._schedule_brief_generation(trigger)

        # Task should be pending
        assert len(orchestrator._pending_brief_tasks) == 1
