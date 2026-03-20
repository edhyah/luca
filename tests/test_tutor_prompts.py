"""Tests for tutor prompts and context building."""

import pytest

from luca.curriculum.models import (
    BKTParameters,
    CommonError,
    Concept,
    Curriculum,
    Revelation,
    ScaffoldStep,
)
from luca.pipeline.pattern_matcher import MatchResult, MatchSignal
from luca.student.session_state import SessionState
from luca.student.teaching_brief import TeachingBrief
from luca.tutor.context_builder import ContextBuilder, build_initial_context
from luca.tutor.context_format import EmotionalTone, TurnContext, compute_emotional_tone
from luca.tutor.prompts.few_shot_examples import (
    FEW_SHOT_EXAMPLES,
    format_examples_for_prompt,
    get_all_examples_formatted,
    get_examples_for_scenario,
)
from luca.tutor.prompts.system_prompt import TUTOR_SYSTEM_PROMPT, build_system_prompt


# Fixtures
@pytest.fixture
def sample_bkt_params() -> BKTParameters:
    """Create sample BKT parameters."""
    return BKTParameters(
        p_init=0.0,
        p_learn=0.3,
        p_guess=0.1,
        p_slip=0.1,
        p_forget=0.05,
    )


@pytest.fixture
def sample_scaffold_step() -> ScaffoldStep:
    """Create a sample scaffold step."""
    return ScaffoldStep(
        step_id="verb_es_01",
        tutor_prompt="How would you say 'it is normal'?",
        expected_answers=["es normal"],
        answer_notes="Spanish typically omits the subject pronoun.",
        difficulty=2,
        hints=["Start with the word for 'is'...", "It's just two words: 'is' + 'normal'..."],
        revelation=None,
    )


@pytest.fixture
def sample_scaffold_step_with_revelation() -> ScaffoldStep:
    """Create a scaffold step with revelation."""
    return ScaffoldStep(
        step_id="cognate_al_03",
        tutor_prompt="And 'natural'?",
        expected_answers=["natural"],
        answer_notes="Pronounced nah-too-RAHL.",
        difficulty=1,
        hints=[],
        revelation=Revelation(
            pattern_name="suffix_al_conversion",
            first_encounter_script="Words ending in -al are often identical in Spanish.",
            review_reference="Remember the rule for words ending in -al?",
        ),
    )


@pytest.fixture
def sample_common_error() -> CommonError:
    """Create a sample common error."""
    return CommonError(
        error_type="adding_it",
        example="it es normal",
        explanation="Student tries to translate 'it' explicitly.",
        tutor_correction_approach="Spanish doesn't need a separate word for 'it' here.",
    )


@pytest.fixture
def sample_concept(
    sample_bkt_params: BKTParameters,
    sample_scaffold_step: ScaffoldStep,
    sample_common_error: CommonError,
) -> Concept:
    """Create a sample concept."""
    return Concept(
        concept_id="verb_es",
        name="The verb 'is' (es)",
        episode=2,
        prerequisites=["cognate_al"],
        scaffold_steps=[sample_scaffold_step],
        common_errors=[sample_common_error],
        bkt_parameters=sample_bkt_params,
    )


@pytest.fixture
def sample_curriculum(sample_concept: Concept) -> Curriculum:
    """Create a sample curriculum."""
    return Curriculum(
        version="1.0.0",
        description="Test curriculum",
        episodes=[2],
        concepts=[sample_concept],
    )


@pytest.fixture
def sample_session_state(sample_curriculum: Curriculum) -> SessionState:
    """Create a session state with sample curriculum."""
    state = SessionState(student_id="test_student", curriculum=sample_curriculum)
    state.advance_concept("verb_es")
    return state


@pytest.fixture
def sample_teaching_brief() -> TeachingBrief:
    """Create a sample teaching brief."""
    return TeachingBrief(
        student_id="test_student",
        strengths=["Quick pattern recognition", "Good memory"],
        challenges=["Pronunciation of R"],
        error_patterns=["English stress patterns"],
        effective_strategies=["Visual analogies"],
        preferred_explanation_style="step-by-step",
    )


@pytest.fixture
def sample_match_result_correct() -> MatchResult:
    """Create a CLEAR_MATCH result."""
    return MatchResult(
        signal=MatchSignal.CLEAR_MATCH,
        score=95.0,
        best_match="es normal",
        diff=None,
    )


@pytest.fixture
def sample_match_result_incorrect() -> MatchResult:
    """Create a CLEAR_MISS result."""
    return MatchResult(
        signal=MatchSignal.CLEAR_MISS,
        score=45.0,
        best_match="es normal",
        diff="extra: it",
    )


@pytest.fixture
def sample_match_result_ambiguous() -> MatchResult:
    """Create an AMBIGUOUS result."""
    return MatchResult(
        signal=MatchSignal.AMBIGUOUS,
        score=72.0,
        best_match="es normal",
        diff="minor spelling differences",
    )


# Tests for TurnContext
class TestTurnContext:
    """Tests for TurnContext dataclass."""

    def test_create_basic_context(self, sample_scaffold_step: ScaffoldStep) -> None:
        """Test creating a basic TurnContext."""
        context = TurnContext(
            concept_id="verb_es",
            concept_name="The verb 'is' (es)",
            step_index=0,
            step_id=sample_scaffold_step.step_id,
            tutor_prompt=sample_scaffold_step.tutor_prompt,
            expected_answers=sample_scaffold_step.expected_answers,
            difficulty=sample_scaffold_step.difficulty,
            hints=sample_scaffold_step.hints,
            evaluation_signal=MatchSignal.CLEAR_MATCH,
            student_transcript="es normal",
            match_score=95.0,
            diff=None,
        )

        assert context.concept_id == "verb_es"
        assert context.step_id == "verb_es_01"
        assert context.evaluation_signal == MatchSignal.CLEAR_MATCH
        assert context.match_score == 95.0

    def test_format_for_prompt_basic(self, sample_scaffold_step: ScaffoldStep) -> None:
        """Test formatting context for prompt injection."""
        context = TurnContext(
            concept_id="verb_es",
            concept_name="The verb 'is' (es)",
            step_index=0,
            step_id="verb_es_01",
            tutor_prompt="How would you say 'it is normal'?",
            expected_answers=["es normal"],
            difficulty=2,
            hints=["Start with the word for 'is'..."],
            evaluation_signal=MatchSignal.CLEAR_MATCH,
            student_transcript="es normal",
            match_score=95.0,
            diff=None,
        )

        formatted = context.format_for_prompt()

        assert "verb_es" in formatted
        assert "The verb 'is' (es)" in formatted
        assert "How would you say 'it is normal'?" in formatted
        assert '"es normal"' in formatted
        assert "CLEAR_MATCH" in formatted
        assert "95.0%" in formatted

    def test_format_for_prompt_with_hints(self) -> None:
        """Test formatting includes available hints."""
        context = TurnContext(
            concept_id="verb_es",
            concept_name="The verb 'is'",
            step_index=0,
            step_id="verb_es_01",
            tutor_prompt="How would you say 'it is normal'?",
            expected_answers=["es normal"],
            difficulty=2,
            hints=["Hint 1", "Hint 2", "Hint 3"],
            evaluation_signal=MatchSignal.CLEAR_MATCH,
            student_transcript="",
            match_score=0.0,
            diff=None,
        )

        formatted = context.format_for_prompt()

        assert "Available Hints" in formatted
        assert "Hint 1" in formatted
        assert "Hint 2" in formatted
        assert "Hint 3" in formatted

    def test_format_for_prompt_with_revelation(self) -> None:
        """Test formatting includes revelation prompt."""
        context = TurnContext(
            concept_id="cognate_al",
            concept_name="Latin Cognates: -al",
            step_index=2,
            step_id="cognate_al_03",
            tutor_prompt="And 'natural'?",
            expected_answers=["natural"],
            difficulty=1,
            hints=[],
            evaluation_signal=MatchSignal.CLEAR_MATCH,
            student_transcript="natural",
            match_score=98.0,
            diff=None,
            revelation_prompt="Words ending in -al are often identical in Spanish.",
            is_first_encounter=True,
        )

        formatted = context.format_for_prompt()

        assert "Pattern Revelation" in formatted
        assert "FIRST ENCOUNTER" in formatted
        assert "Words ending in -al are often identical" in formatted

    def test_format_for_prompt_with_common_errors(
        self, sample_common_error: CommonError
    ) -> None:
        """Test formatting includes common errors."""
        context = TurnContext(
            concept_id="verb_es",
            concept_name="The verb 'is'",
            step_index=0,
            step_id="verb_es_01",
            tutor_prompt="How would you say 'it is normal'?",
            expected_answers=["es normal"],
            difficulty=2,
            hints=[],
            evaluation_signal=MatchSignal.CLEAR_MISS,
            student_transcript="it es normal",
            match_score=45.0,
            diff="extra: it",
            common_errors=[sample_common_error],
        )

        formatted = context.format_for_prompt()

        assert "Common Errors" in formatted
        assert "adding_it" in formatted
        assert "it es normal" in formatted

    def test_format_for_prompt_ambiguous_flag(self) -> None:
        """Test formatting includes AMBIGUOUS evaluation flag."""
        context = TurnContext(
            concept_id="verb_es",
            concept_name="The verb 'is'",
            step_index=0,
            step_id="verb_es_01",
            tutor_prompt="How would you say 'it is normal'?",
            expected_answers=["es normal"],
            difficulty=2,
            hints=[],
            evaluation_signal=MatchSignal.AMBIGUOUS,
            student_transcript="ess normal",
            match_score=72.0,
            diff="minor spelling",
            requires_inline_evaluation=True,
        )

        formatted = context.format_for_prompt()

        assert "AMBIGUOUS" in formatted
        assert "You must evaluate" in formatted

    def test_format_for_prompt_with_teaching_brief(self) -> None:
        """Test formatting includes teaching brief."""
        context = TurnContext(
            concept_id="verb_es",
            concept_name="The verb 'is'",
            step_index=0,
            step_id="verb_es_01",
            tutor_prompt="Test",
            expected_answers=["test"],
            difficulty=1,
            hints=[],
            evaluation_signal=MatchSignal.CLEAR_MATCH,
            student_transcript="test",
            match_score=100.0,
            diff=None,
            teaching_brief="Strengths: Quick pattern recognition",
        )

        formatted = context.format_for_prompt()

        assert "Student Profile" in formatted
        assert "Quick pattern recognition" in formatted


# Tests for compute_emotional_tone
class TestComputeEmotionalTone:
    """Tests for emotional tone computation."""

    def test_neutral_with_few_responses(self) -> None:
        """Test neutral tone when not enough data."""
        tone = compute_emotional_tone(streak_length=2, error_rate=0.0, response_count=2)
        assert tone == EmotionalTone.NEUTRAL

    def test_ease_off_high_error_rate(self) -> None:
        """Test ease_off tone with high error rate."""
        tone = compute_emotional_tone(streak_length=0, error_rate=0.6, response_count=10)
        assert tone == EmotionalTone.EASE_OFF

    def test_push_harder_strong_streak(self) -> None:
        """Test push_harder tone with strong streak."""
        tone = compute_emotional_tone(streak_length=5, error_rate=0.1, response_count=10)
        assert tone == EmotionalTone.PUSH_HARDER

    def test_encourage_moderate_errors(self) -> None:
        """Test encourage tone with moderate error rate."""
        tone = compute_emotional_tone(streak_length=1, error_rate=0.35, response_count=10)
        assert tone == EmotionalTone.ENCOURAGE

    def test_neutral_normal_performance(self) -> None:
        """Test neutral tone with normal performance."""
        tone = compute_emotional_tone(streak_length=2, error_rate=0.15, response_count=10)
        assert tone == EmotionalTone.NEUTRAL


# Tests for ContextBuilder
class TestContextBuilder:
    """Tests for ContextBuilder class."""

    def test_build_turn_context_basic(
        self,
        sample_session_state: SessionState,
        sample_match_result_correct: MatchResult,
    ) -> None:
        """Test building basic turn context."""
        builder = ContextBuilder()
        context = builder.build_turn_context(
            session_state=sample_session_state,
            match_result=sample_match_result_correct,
            student_transcript="es normal",
        )

        assert context is not None
        assert context.concept_id == "verb_es"
        assert context.step_id == "verb_es_01"
        assert context.evaluation_signal == MatchSignal.CLEAR_MATCH
        assert context.student_transcript == "es normal"

    def test_build_turn_context_no_concept(self) -> None:
        """Test building context returns None when no concept active."""
        state = SessionState(student_id="test")
        builder = ContextBuilder()

        context = builder.build_turn_context(state)
        assert context is None

    def test_build_turn_context_with_teaching_brief(
        self,
        sample_session_state: SessionState,
        sample_teaching_brief: TeachingBrief,
    ) -> None:
        """Test building context includes teaching brief."""
        builder = ContextBuilder()
        builder.set_teaching_brief(sample_teaching_brief)

        context = builder.build_turn_context(sample_session_state)

        assert context is not None
        assert context.teaching_brief is not None
        assert "Quick pattern recognition" in context.teaching_brief

    def test_hint_tracking(self, sample_session_state: SessionState) -> None:
        """Test hint tracking during thinking pauses."""
        builder = ContextBuilder()

        # Record hints given
        builder.record_hint_given()
        builder.record_hint_given()

        context = builder.build_turn_context(sample_session_state)

        assert context is not None
        assert context.thinking_pause_hints_given == 2

        # Reset for new step
        builder.reset_hints()
        context = builder.build_turn_context(sample_session_state)

        assert context.thinking_pause_hints_given == 0

    def test_revelation_first_encounter(
        self, sample_curriculum: Curriculum, sample_bkt_params: BKTParameters
    ) -> None:
        """Test revelation is marked as first encounter."""
        # Add concept with revelation
        concept = Concept(
            concept_id="cognate_al",
            name="Latin Cognates: -al",
            episode=2,
            prerequisites=[],
            scaffold_steps=[
                ScaffoldStep(
                    step_id="cognate_al_03",
                    tutor_prompt="And 'natural'?",
                    expected_answers=["natural"],
                    difficulty=1,
                    hints=[],
                    revelation=Revelation(
                        pattern_name="suffix_al_conversion",
                        first_encounter_script="Words ending in -al are often identical.",
                        review_reference="Remember the -al rule?",
                    ),
                )
            ],
            common_errors=[],
            bkt_parameters=sample_bkt_params,
        )

        curriculum = Curriculum(
            version="1.0.0",
            description="Test",
            episodes=[2],
            concepts=[concept],
        )

        state = SessionState(student_id="test", curriculum=curriculum)
        state.advance_concept("cognate_al")

        builder = ContextBuilder()
        context = builder.build_turn_context(state)

        assert context is not None
        assert context.revelation_prompt is not None
        assert context.is_first_encounter is True
        assert "Words ending in -al are often identical" in context.revelation_prompt

    def test_revelation_review_encounter(
        self, sample_curriculum: Curriculum, sample_bkt_params: BKTParameters
    ) -> None:
        """Test revelation shows review text on subsequent encounters."""
        concept = Concept(
            concept_id="cognate_al",
            name="Latin Cognates: -al",
            episode=2,
            prerequisites=[],
            scaffold_steps=[
                ScaffoldStep(
                    step_id="cognate_al_03",
                    tutor_prompt="And 'natural'?",
                    expected_answers=["natural"],
                    difficulty=1,
                    hints=[],
                    revelation=Revelation(
                        pattern_name="suffix_al_conversion",
                        first_encounter_script="First encounter text.",
                        review_reference="Review text.",
                    ),
                )
            ],
            common_errors=[],
            bkt_parameters=sample_bkt_params,
        )

        curriculum = Curriculum(
            version="1.0.0",
            description="Test",
            episodes=[2],
            concepts=[concept],
        )

        state = SessionState(student_id="test", curriculum=curriculum)
        state.advance_concept("cognate_al")

        builder = ContextBuilder()
        # Mark as already seen
        builder.mark_revelation_seen("suffix_al_conversion")

        context = builder.build_turn_context(state)

        assert context is not None
        assert context.is_first_encounter is False
        assert context.revelation_prompt == "Review text."

    def test_build_system_prompt(self, sample_session_state: SessionState) -> None:
        """Test building complete system prompt."""
        builder = ContextBuilder()
        context = builder.build_turn_context(sample_session_state)

        prompt = builder.build_system_prompt(context)

        # Check base prompt elements
        assert "You are Luca" in prompt
        assert "Language Transfer" in prompt
        assert "Guide discovery" in prompt

        # Check context was injected
        assert "verb_es" in prompt
        assert "How would you say 'it is normal'?" in prompt

    def test_build_system_prompt_no_context(self) -> None:
        """Test building system prompt without context."""
        builder = ContextBuilder()
        prompt = builder.build_system_prompt(None)

        assert "You are Luca" in prompt
        assert "No specific lesson loaded" in prompt


# Tests for build_initial_context
class TestBuildInitialContext:
    """Tests for build_initial_context helper."""

    def test_build_initial_context_basic(
        self, sample_session_state: SessionState
    ) -> None:
        """Test building initial context."""
        builder, context = build_initial_context(sample_session_state)

        assert builder is not None
        assert context is not None
        assert context.concept_id == "verb_es"

    def test_build_initial_context_with_brief(
        self,
        sample_session_state: SessionState,
        sample_teaching_brief: TeachingBrief,
    ) -> None:
        """Test building initial context with teaching brief."""
        builder, context = build_initial_context(
            sample_session_state,
            teaching_brief=sample_teaching_brief,
        )

        assert context is not None
        assert context.teaching_brief is not None


# Tests for system prompt
class TestSystemPrompt:
    """Tests for system prompt template."""

    def test_system_prompt_contains_personality(self) -> None:
        """Test system prompt contains personality section."""
        assert "Your Personality" in TUTOR_SYSTEM_PROMPT
        assert "Patient" in TUTOR_SYSTEM_PROMPT
        assert "Warm" in TUTOR_SYSTEM_PROMPT

    def test_system_prompt_contains_method(self) -> None:
        """Test system prompt contains Language Transfer method."""
        assert "Language Transfer Method" in TUTOR_SYSTEM_PROMPT
        assert "Guide discovery" in TUTOR_SYSTEM_PROMPT
        assert "Build on English cognates" in TUTOR_SYSTEM_PROMPT

    def test_system_prompt_contains_format_rules(self) -> None:
        """Test system prompt contains output format rules."""
        assert "Response Format Rules" in TUTOR_SYSTEM_PROMPT
        assert "Keep turns short" in TUTOR_SYSTEM_PROMPT
        assert "text-to-speech" in TUTOR_SYSTEM_PROMPT

    def test_system_prompt_contains_situation_handling(self) -> None:
        """Test system prompt contains situation handling."""
        assert "CLEAR_MATCH" in TUTOR_SYSTEM_PROMPT
        assert "CLEAR_MISS" in TUTOR_SYSTEM_PROMPT
        assert "AMBIGUOUS" in TUTOR_SYSTEM_PROMPT

    def test_system_prompt_has_placeholders(self) -> None:
        """Test system prompt has context placeholders."""
        assert "{lesson_context}" in TUTOR_SYSTEM_PROMPT
        assert "{student_profile}" in TUTOR_SYSTEM_PROMPT

    def test_build_system_prompt_fills_placeholders(self) -> None:
        """Test build_system_prompt fills placeholders."""
        prompt = build_system_prompt(
            lesson_context="Test lesson context",
            student_profile="Test student profile",
        )

        assert "{lesson_context}" not in prompt
        assert "{student_profile}" not in prompt
        assert "Test lesson context" in prompt
        assert "Test student profile" in prompt


# Tests for few-shot examples
class TestFewShotExamples:
    """Tests for few-shot examples."""

    def test_examples_exist(self) -> None:
        """Test that examples are defined."""
        assert len(FEW_SHOT_EXAMPLES) >= 9

    def test_all_scenarios_covered(self) -> None:
        """Test that all required scenarios are covered."""
        scenarios = {ex.scenario for ex in FEW_SHOT_EXAMPLES}

        required = {
            "correct_answer",
            "incorrect_answer",
            "partial_answer",
            "student_frustration",
            "meta_question",
            "concept_boundary",
            "ambiguous_evaluation",
            "revelation_framing",
            "post_silence_hints",
        }

        assert required.issubset(scenarios)

    def test_get_examples_for_scenario(self) -> None:
        """Test filtering examples by scenario."""
        examples = get_examples_for_scenario("correct_answer")

        assert len(examples) >= 1
        assert all(ex.scenario == "correct_answer" for ex in examples)

    def test_format_examples_for_prompt(self) -> None:
        """Test formatting examples for prompt."""
        examples = get_examples_for_scenario("correct_answer")
        formatted = format_examples_for_prompt(examples)

        assert "Example 1" in formatted
        assert "Context:" in formatted
        assert "Student:" in formatted
        assert "Luca:" in formatted

    def test_get_all_examples_formatted(self) -> None:
        """Test getting all examples formatted."""
        formatted = get_all_examples_formatted()

        assert len(formatted) > 0
        assert "correct_answer" in formatted.lower() or "Correct Answer" in formatted
        assert "incorrect_answer" in formatted.lower() or "Incorrect Answer" in formatted

    def test_examples_have_required_fields(self) -> None:
        """Test all examples have required fields."""
        for ex in FEW_SHOT_EXAMPLES:
            assert ex.scenario
            assert ex.context
            # student_input can be empty for initial prompts
            assert ex.tutor_response

    def test_example_responses_are_voice_optimized(self) -> None:
        """Test example responses are suitable for voice output."""
        for ex in FEW_SHOT_EXAMPLES:
            response = ex.tutor_response

            # Should not have bullet points
            assert "- " not in response or response.count("- ") <= 1

            # Should not have markdown formatting
            assert "**" not in response
            assert "__" not in response

            # Should be reasonably short (voice-optimized)
            # Count actual sentence endings, ignoring ellipses
            # Remove ellipses first to avoid false counts
            clean_response = response.replace("...", "")
            sentences = (
                clean_response.count(".")
                + clean_response.count("?")
                + clean_response.count("!")
            )
            assert sentences <= 8, f"Response too long: {response}"


# Tests for edge cases
class TestEdgeCases:
    """Tests for edge cases in context building."""

    def test_no_teaching_brief(self, sample_session_state: SessionState) -> None:
        """Test context building without teaching brief."""
        builder = ContextBuilder()
        context = builder.build_turn_context(sample_session_state)

        assert context is not None
        assert context.teaching_brief is None

    def test_no_hints_available(
        self, sample_curriculum: Curriculum, sample_bkt_params: BKTParameters
    ) -> None:
        """Test context with no hints available."""
        concept = Concept(
            concept_id="simple",
            name="Simple Concept",
            episode=2,
            prerequisites=[],
            scaffold_steps=[
                ScaffoldStep(
                    step_id="simple_01",
                    tutor_prompt="Say 'hola'",
                    expected_answers=["hola"],
                    difficulty=1,
                    hints=[],  # No hints
                )
            ],
            common_errors=[],
            bkt_parameters=sample_bkt_params,
        )

        curriculum = Curriculum(
            version="1.0.0",
            description="Test",
            episodes=[2],
            concepts=[concept],
        )

        state = SessionState(student_id="test", curriculum=curriculum)
        state.advance_concept("simple")

        builder = ContextBuilder()
        context = builder.build_turn_context(state)

        assert context is not None
        assert context.hints == []

    def test_no_common_errors(
        self, sample_curriculum: Curriculum, sample_bkt_params: BKTParameters
    ) -> None:
        """Test context with no common errors defined."""
        concept = Concept(
            concept_id="simple",
            name="Simple Concept",
            episode=2,
            prerequisites=[],
            scaffold_steps=[
                ScaffoldStep(
                    step_id="simple_01",
                    tutor_prompt="Say 'hola'",
                    expected_answers=["hola"],
                    difficulty=1,
                    hints=[],
                )
            ],
            common_errors=[],  # No common errors
            bkt_parameters=sample_bkt_params,
        )

        curriculum = Curriculum(
            version="1.0.0",
            description="Test",
            episodes=[2],
            concepts=[concept],
        )

        state = SessionState(student_id="test", curriculum=curriculum)
        state.advance_concept("simple")

        builder = ContextBuilder()
        context = builder.build_turn_context(state)

        assert context is not None
        assert context.common_errors == []

    def test_empty_student_transcript(self, sample_session_state: SessionState) -> None:
        """Test context with empty student transcript (initial prompt)."""
        builder = ContextBuilder()
        context = builder.build_turn_context(
            sample_session_state,
            match_result=None,
            student_transcript="",
        )

        assert context is not None
        assert context.student_transcript == ""
        assert context.evaluation_signal == MatchSignal.AMBIGUOUS  # Default

    def test_multiple_expected_answers(
        self, sample_curriculum: Curriculum, sample_bkt_params: BKTParameters
    ) -> None:
        """Test context with multiple expected answers."""
        concept = Concept(
            concept_id="multi",
            name="Multiple Answers",
            episode=2,
            prerequisites=[],
            scaffold_steps=[
                ScaffoldStep(
                    step_id="multi_01",
                    tutor_prompt="Say something",
                    expected_answers=["answer1", "answer2", "answer3"],
                    difficulty=1,
                    hints=[],
                )
            ],
            common_errors=[],
            bkt_parameters=sample_bkt_params,
        )

        curriculum = Curriculum(
            version="1.0.0",
            description="Test",
            episodes=[2],
            concepts=[concept],
        )

        state = SessionState(student_id="test", curriculum=curriculum)
        state.advance_concept("multi")

        builder = ContextBuilder()
        context = builder.build_turn_context(state)

        assert context is not None
        assert len(context.expected_answers) == 3

        formatted = context.format_for_prompt()
        assert '"answer1"' in formatted
        assert '"answer2"' in formatted
        assert '"answer3"' in formatted
