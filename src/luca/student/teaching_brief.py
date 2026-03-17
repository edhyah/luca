"""Teaching briefs for personalized instruction."""

from dataclasses import dataclass, field

from luca.utils.logging import get_logger

logger = get_logger("student.teaching_brief")


@dataclass
class TeachingBrief:
    """Summarized insights about a student for personalized teaching.

    Generated periodically by analyzing session history with Gemini Flash.
    """

    student_id: str

    # Learning patterns
    strengths: list[str] = field(default_factory=list)
    challenges: list[str] = field(default_factory=list)
    preferred_explanation_style: str = ""

    # Engagement patterns
    optimal_session_length: int = 20  # minutes
    response_time_pattern: str = "average"

    # Common errors
    error_patterns: list[str] = field(default_factory=list)

    # What works
    effective_strategies: list[str] = field(default_factory=list)

    # Raw summary for context
    summary: str = ""

    def to_prompt_context(self) -> str:
        """Convert teaching brief to context string for tutor prompt."""
        sections = []

        if self.strengths:
            sections.append(f"Strengths: {', '.join(self.strengths)}")

        if self.challenges:
            sections.append(f"Challenges: {', '.join(self.challenges)}")

        if self.error_patterns:
            sections.append(f"Common errors: {', '.join(self.error_patterns)}")

        if self.effective_strategies:
            sections.append(f"What works: {', '.join(self.effective_strategies)}")

        if self.preferred_explanation_style:
            sections.append(f"Prefers: {self.preferred_explanation_style}")

        return "\n".join(sections) if sections else "No teaching brief available yet."


async def generate_teaching_brief(
    student_id: str,
    session_history: list[dict],
) -> TeachingBrief:
    """Generate a teaching brief from session history using Gemini Flash.

    This should be called periodically (e.g., after each session) to update
    the teaching brief with new insights.
    """
    # TODO: Implement Gemini Flash API call to analyze session history
    logger.info(f"Generating teaching brief for student {student_id}")
    return TeachingBrief(student_id=student_id)
