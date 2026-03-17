"""Context builder for tutor prompts."""

from luca.utils.logging import get_logger

logger = get_logger("tutor.context_builder")


class ContextBuilder:
    """Builds context for tutor prompts from curriculum and student state."""

    def __init__(self) -> None:
        self.current_concept: dict | None = None
        self.student_history: list[dict] = []

    def set_concept(self, concept: dict) -> None:
        """Set the current concept being taught."""
        self.current_concept = concept

    def add_exchange(self, role: str, content: str) -> None:
        """Add an exchange to the conversation history."""
        self.student_history.append({"role": role, "content": content})

    def build_lesson_context(self) -> str:
        """Build the lesson context string for the prompt."""
        if not self.current_concept:
            return ""

        return f"""
Concept: {self.current_concept.get('name', 'Unknown')}
Explanation: {self.current_concept.get('explanation', '')}
Examples: {self.current_concept.get('examples', [])}
Expected Patterns: {self.current_concept.get('expected_patterns', [])}
"""

    def build_student_profile(self) -> str:
        """Build the student profile string for the prompt."""
        # TODO: Integrate with student model
        return "Student profile not yet available."
