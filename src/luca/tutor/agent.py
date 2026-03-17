"""Claude integration for the tutor agent."""

from luca.utils.config import get_settings
from luca.utils.logging import get_logger

logger = get_logger("tutor.agent")


class TutorAgent:
    """Tutor agent powered by Claude for language instruction."""

    def __init__(self) -> None:
        self.settings = get_settings()
        # TODO: Initialize Anthropic client

    async def generate_response(
        self,
        student_input: str,
        context: dict,
    ) -> str:
        """Generate a tutor response to student input."""
        # TODO: Implement Claude API call with context
        logger.debug(f"Generating response for: {student_input[:50]}...")
        return ""

    async def evaluate_response(
        self,
        expected: str,
        actual: str,
    ) -> dict:
        """Evaluate student response against expected answer."""
        # TODO: Implement evaluation logic
        return {"correct": False, "feedback": ""}
