"""Context format specification for tutor prompts.

Defines the exact format the orchestrator injects per turn,
providing the tutor with all information needed to respond appropriately.
"""

from dataclasses import dataclass, field
from enum import Enum

from luca.curriculum.models import CommonError
from luca.pipeline.pattern_matcher import MatchSignal


class EmotionalTone(str, Enum):
    """Emotional calibration for tutor responses."""

    ENCOURAGE = "encourage"  # Student struggling, needs support
    NEUTRAL = "neutral"  # Normal progression
    EASE_OFF = "ease_off"  # High error rate, reduce pressure
    PUSH_HARDER = "push_harder"  # Strong streak, can challenge more


@dataclass
class TurnContext:
    """Complete context for a single tutor turn.

    This dataclass contains all information the tutor needs to generate
    an appropriate response, including curriculum position, evaluation
    results, emotional state, and teaching guidance.
    """

    # Current scaffold position
    concept_id: str
    concept_name: str
    step_index: int
    step_id: str
    tutor_prompt: str  # What to ask the student
    expected_answers: list[str]
    difficulty: int  # 1-5
    hints: list[str]

    # Evaluation result from pattern matcher
    evaluation_signal: MatchSignal  # CLEAR_MATCH, CLEAR_MISS, AMBIGUOUS
    student_transcript: str  # Raw STT output
    match_score: float  # 0-100
    diff: str | None  # For CLEAR_MISS: what's wrong

    # For AMBIGUOUS: tutor must evaluate inline
    requires_inline_evaluation: bool = False

    # Revelation (if applicable)
    revelation_prompt: str | None = None  # Pattern description to name
    is_first_encounter: bool = True  # First time vs review

    # Post-silence state
    thinking_pause_hints_given: int = 0  # 0, 1, 2, or 3

    # Emotional calibration
    streak_length: int = 0
    error_rate: float = 0.0  # 0.0 - 1.0
    emotional_tone: EmotionalTone = EmotionalTone.NEUTRAL

    # Teaching brief (if available)
    teaching_brief: str | None = None

    # Common errors for this concept
    common_errors: list[CommonError] = field(default_factory=list)

    # Answer notes for evaluation guidance
    answer_notes: str = ""

    def format_for_prompt(self) -> str:
        """Convert TurnContext to string for injection into system prompt.

        Returns a structured, readable format optimized for LLM comprehension.
        """
        sections = []

        # Current position
        sections.append(f"""## Current Position
Concept: {self.concept_name} ({self.concept_id})
Step: {self.step_index + 1} ({self.step_id})
Difficulty: {self.difficulty}/5""")

        # The prompt to deliver (if this is a new step)
        sections.append(f"""## Your Prompt
{self.tutor_prompt}""")

        # Expected answers
        expected = ", ".join(f'"{a}"' for a in self.expected_answers)
        sections.append(f"""## Expected Answers
{expected}""")

        if self.answer_notes:
            sections.append(f"Notes: {self.answer_notes}")

        # Available hints
        if self.hints:
            hint_list = "\n".join(f"  {i+1}. {h}" for i, h in enumerate(self.hints))
            sections.append(f"""## Available Hints
{hint_list}""")

        # Student response and evaluation
        if self.student_transcript:
            sections.append(f"""## Student Response
Transcript: "{self.student_transcript}"
Evaluation: {self.evaluation_signal.value.upper()}
Match Score: {self.match_score:.1f}%""")

            if self.diff:
                sections.append(f"Diff: {self.diff}")

            if self.requires_inline_evaluation:
                sections.append(
                    ">>> AMBIGUOUS: You must evaluate if this answer is acceptable. <<<"
                )

        # Hints already given during thinking pause
        if self.thinking_pause_hints_given > 0:
            sections.append(
                f"""## Hints Already Given
You have already given {self.thinking_pause_hints_given} hint(s) during the thinking pause.
Next hint to give (if needed): {self.hints[self.thinking_pause_hints_given] if self.thinking_pause_hints_given < len(self.hints) else "No more hints available."}"""
            )

        # Revelation
        if self.revelation_prompt:
            encounter_type = "FIRST ENCOUNTER" if self.is_first_encounter else "REVIEW"
            sections.append(f"""## Pattern Revelation ({encounter_type})
{self.revelation_prompt}""")

        # Emotional calibration
        sections.append(f"""## Emotional Calibration
Streak: {self.streak_length} correct in a row
Error Rate: {self.error_rate:.0%} (recent window)
Tone: {self.emotional_tone.value.upper()}""")

        # Common errors to watch for
        if self.common_errors:
            error_list = []
            for err in self.common_errors:
                error_list.append(
                    f"  - {err.error_type}: {err.example}\n"
                    f"    Approach: {err.tutor_correction_approach}"
                )
            sections.append(f"""## Common Errors to Watch For
{chr(10).join(error_list)}""")

        # Teaching brief
        if self.teaching_brief:
            sections.append(f"""## Student Profile
{self.teaching_brief}""")

        return "\n\n".join(sections)


def compute_emotional_tone(
    streak_length: int,
    error_rate: float,
    response_count: int,
) -> EmotionalTone:
    """Compute emotional tone based on student performance.

    Args:
        streak_length: Current streak of correct answers.
        error_rate: Error rate over sliding window (0.0-1.0).
        response_count: Total responses in the window.

    Returns:
        Appropriate EmotionalTone for the situation.
    """
    # Not enough data to calibrate
    if response_count < 3:
        return EmotionalTone.NEUTRAL

    # High error rate - ease off, reduce pressure
    if error_rate >= 0.5:
        return EmotionalTone.EASE_OFF

    # Strong streak - can push harder
    if streak_length >= 4:
        return EmotionalTone.PUSH_HARDER

    # Recent errors but not overwhelming - encourage
    if error_rate >= 0.3:
        return EmotionalTone.ENCOURAGE

    return EmotionalTone.NEUTRAL
