"""Context builder for tutor prompts.

Assembles TurnContext from session state and evaluation results,
and formats it for injection into the system prompt.
"""

from luca.curriculum.models import CommonError, Concept, ScaffoldStep
from luca.pipeline.pattern_matcher import MatchResult, MatchSignal
from luca.student.session_state import SessionState
from luca.student.teaching_brief import TeachingBrief
from luca.tutor.context_format import EmotionalTone, TurnContext, compute_emotional_tone
from luca.tutor.prompts.system_prompt import build_system_prompt
from luca.utils.logging import get_logger

logger = get_logger("tutor.context_builder")


class ContextBuilder:
    """Builds context for tutor prompts from curriculum and student state."""

    def __init__(self) -> None:
        self.current_concept: Concept | None = None
        self.current_step: ScaffoldStep | None = None
        self.teaching_brief: TeachingBrief | None = None
        self.thinking_pause_hints_given: int = 0
        self._seen_revelations: set[str] = set()

    def set_concept(self, concept: Concept) -> None:
        """Set the current concept being taught."""
        self.current_concept = concept

    def set_step(self, step: ScaffoldStep) -> None:
        """Set the current scaffold step."""
        self.current_step = step

    def set_teaching_brief(self, brief: TeachingBrief) -> None:
        """Set the teaching brief for the current student."""
        self.teaching_brief = brief

    def record_hint_given(self) -> None:
        """Record that a hint was given during thinking pause."""
        self.thinking_pause_hints_given += 1

    def reset_hints(self) -> None:
        """Reset hint counter for a new step."""
        self.thinking_pause_hints_given = 0

    def mark_revelation_seen(self, pattern_name: str) -> None:
        """Mark a revelation pattern as seen (no longer first encounter)."""
        self._seen_revelations.add(pattern_name)

    def is_first_encounter(self, pattern_name: str) -> bool:
        """Check if this is the first encounter with a revelation pattern."""
        return pattern_name not in self._seen_revelations

    def build_turn_context(
        self,
        session_state: SessionState,
        match_result: MatchResult | None = None,
        student_transcript: str = "",
    ) -> TurnContext | None:
        """Build a TurnContext from current state and evaluation result.

        Args:
            session_state: Current session state with curriculum position and stats.
            match_result: Result from pattern matcher (None if no response yet).
            student_transcript: Raw STT transcript of student's response.

        Returns:
            TurnContext ready for prompt injection, or None if no concept is active.
        """
        # Get current concept and step from session state
        concept = self._get_concept(session_state)
        if concept is None:
            logger.warning("No active concept, cannot build context")
            return None

        step = session_state.get_current_step()
        if step is None:
            logger.warning("No active step, cannot build context")
            return None

        # Compute emotional tone
        emotional_tone = compute_emotional_tone(
            streak_length=session_state.get_streak(),
            error_rate=session_state.get_error_rate(),
            response_count=session_state.sliding_window.response_count,
        )

        # Handle revelation
        revelation_prompt = None
        is_first_encounter = True
        if step.revelation:
            pattern_name = step.revelation.pattern_name
            is_first_encounter = self.is_first_encounter(pattern_name)
            if is_first_encounter:
                revelation_prompt = step.revelation.first_encounter_script
            else:
                revelation_prompt = step.revelation.review_reference

        # Build the context
        context = TurnContext(
            # Current position
            concept_id=concept.concept_id,
            concept_name=concept.name,
            step_index=session_state.current_step_index,
            step_id=step.step_id,
            tutor_prompt=step.tutor_prompt,
            expected_answers=step.expected_answers,
            difficulty=step.difficulty,
            hints=step.hints,
            # Evaluation
            evaluation_signal=match_result.signal if match_result else MatchSignal.AMBIGUOUS,
            student_transcript=student_transcript,
            match_score=match_result.score if match_result else 0.0,
            diff=match_result.diff if match_result else None,
            requires_inline_evaluation=(
                match_result.signal == MatchSignal.AMBIGUOUS if match_result else False
            ),
            # Revelation
            revelation_prompt=revelation_prompt,
            is_first_encounter=is_first_encounter,
            # Hints state
            thinking_pause_hints_given=self.thinking_pause_hints_given,
            # Emotional calibration
            streak_length=session_state.get_streak(),
            error_rate=session_state.get_error_rate(),
            emotional_tone=emotional_tone,
            # Teaching brief
            teaching_brief=(
                self.teaching_brief.to_prompt_context() if self.teaching_brief else None
            ),
            # Common errors
            common_errors=concept.common_errors,
            # Answer notes
            answer_notes=step.answer_notes,
        )

        return context

    def _get_concept(self, session_state: SessionState) -> Concept | None:
        """Get the current concept from session state."""
        if session_state.curriculum is None:
            return self.current_concept
        if session_state.current_concept_id is None:
            return self.current_concept
        return session_state.curriculum.get_concept(session_state.current_concept_id)

    def format_for_prompt(self, context: TurnContext) -> str:
        """Format a TurnContext as a string for prompt injection.

        Args:
            context: The TurnContext to format.

        Returns:
            Formatted string for injection into the system prompt.
        """
        return context.format_for_prompt()

    def build_system_prompt(
        self,
        context: TurnContext | None = None,
    ) -> str:
        """Build the complete system prompt with context.

        Args:
            context: TurnContext to inject, or None for base prompt.

        Returns:
            Complete system prompt ready for the LLM.
        """
        lesson_context = ""
        student_profile = ""

        if context:
            lesson_context = self.format_for_prompt(context)
            if context.teaching_brief:
                student_profile = context.teaching_brief

        return build_system_prompt(
            lesson_context=lesson_context,
            student_profile=student_profile,
        )

    def build_lesson_context(self) -> str:
        """Build the lesson context string for the prompt.

        Legacy method for backwards compatibility.
        Prefer using build_turn_context() for full context.
        """
        if not self.current_concept:
            return ""

        return f"""
Concept: {self.current_concept.name}
Step: {self.current_step.step_id if self.current_step else 'Unknown'}
Prompt: {self.current_step.tutor_prompt if self.current_step else ''}
Expected: {self.current_step.expected_answers if self.current_step else []}
"""

    def build_student_profile(self) -> str:
        """Build the student profile string for the prompt.

        Legacy method for backwards compatibility.
        Prefer using build_turn_context() for full context.
        """
        if self.teaching_brief:
            return self.teaching_brief.to_prompt_context()
        return "New student, no history yet."


def build_initial_context(
    session_state: SessionState,
    teaching_brief: TeachingBrief | None = None,
) -> tuple[ContextBuilder, TurnContext | None]:
    """Build initial context for a new tutoring turn.

    Convenience function to create a ContextBuilder and initial TurnContext
    from session state.

    Args:
        session_state: Current session state.
        teaching_brief: Optional teaching brief for the student.

    Returns:
        Tuple of (ContextBuilder, TurnContext or None).
    """
    builder = ContextBuilder()

    if teaching_brief:
        builder.set_teaching_brief(teaching_brief)

    context = builder.build_turn_context(session_state)

    return builder, context
