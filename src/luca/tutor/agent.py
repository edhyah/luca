"""Claude integration for the tutor agent.

Provides streaming response generation using the Anthropic API
with prompt caching for efficient context reuse.
"""

from collections.abc import AsyncIterator
from typing import Any

import anthropic

from luca.tutor.context_builder import ContextBuilder
from luca.tutor.context_format import TurnContext
from luca.utils.config import get_settings
from luca.utils.logging import get_logger

logger = get_logger("tutor.agent")

# Model configuration
DEFAULT_MODEL = "claude-sonnet-4-20250514"
MAX_TOKENS = 256  # Keep responses short for voice


class TutorAgent:
    """Tutor agent powered by Claude for language instruction.

    Supports streaming responses with prompt caching for low latency.
    The system prompt is cached to reduce repeat token processing.
    """

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        context_builder: ContextBuilder | None = None,
    ) -> None:
        self.settings = get_settings()
        self.model = model
        self.context_builder = context_builder or ContextBuilder()

        # Initialize Anthropic client
        self._client = anthropic.AsyncAnthropic(
            api_key=self.settings.anthropic_api_key,
        )

        # Cached system prompt (base without context)
        self._cached_system_prompt: str | None = None

    async def generate_response(
        self,
        context: TurnContext,
        user_message: str | None = None,
    ) -> AsyncIterator[str]:
        """Generate a streaming tutor response.

        Args:
            context: TurnContext with current step and evaluation info.
            user_message: Optional explicit user message. If not provided,
                         uses the student transcript from context.

        Yields:
            Text chunks as they stream from the model.
        """
        # Build system prompt with context
        system_prompt = self.context_builder.build_system_prompt(context)

        # Use student transcript as user message if not provided
        message = user_message or context.student_transcript or ""

        # For initial prompts (no student response yet), use a simple trigger
        if not message:
            message = "[Deliver the tutor prompt for this step]"

        logger.debug(f"Generating response for: {message[:50]}...")

        async with self._client.messages.stream(
            model=self.model,
            max_tokens=MAX_TOKENS,
            system=[
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": message}],
        ) as stream:
            async for text in stream.text_stream:
                yield text

    async def generate_response_full(
        self,
        context: TurnContext,
        user_message: str | None = None,
    ) -> str:
        """Generate a complete tutor response (non-streaming).

        Args:
            context: TurnContext with current step and evaluation info.
            user_message: Optional explicit user message.

        Returns:
            Complete response text.
        """
        chunks = []
        async for chunk in self.generate_response(context, user_message):
            chunks.append(chunk)
        return "".join(chunks)

    async def generate_off_script_response(
        self,
        off_script_type: str,
        current_prompt: str,
        hints: list[str],
        hints_given: int,
    ) -> str:
        """Generate a canned response for off-script requests.

        These bypass the LLM for faster response times.

        Args:
            off_script_type: Type of off-script request (repeat, help, etc.)
            current_prompt: The current tutor prompt to repeat if needed.
            hints: Available hints for the current step.
            hints_given: Number of hints already given.

        Returns:
            Pre-canned response text.
        """
        if off_script_type == "repeat":
            return f"Sure. {current_prompt}"

        elif off_script_type == "slow_down":
            return f"Of course, let's slow down. {current_prompt}"

        elif off_script_type == "confusion":
            # Use first hint if available
            if hints and hints_given < len(hints):
                return f"Let me help. {hints[hints_given]}"
            return f"Let me rephrase. {current_prompt}"

        elif off_script_type == "help":
            # Deliver next available hint
            if hints_given < len(hints):
                return hints[hints_given]
            return "Let me break it down for you."

        elif off_script_type == "skip":
            return "Alright, let's move on."

        return ""

    async def evaluate_response(
        self,
        expected: str,
        actual: str,
    ) -> dict[str, Any]:
        """Evaluate student response against expected answer.

        This is a fallback for AMBIGUOUS cases that need LLM evaluation.

        Args:
            expected: The expected answer.
            actual: The student's actual response.

        Returns:
            Dict with 'correct' bool and optional 'feedback' string.
        """
        prompt = f"""Evaluate if the student's answer is acceptable.

Expected answer: "{expected}"
Student said: "{actual}"

Consider:
- Is the core meaning correct even if pronunciation differs?
- Are minor variations acceptable (articles, pronouns)?
- For spoken Spanish, accent marks won't be audible.

Respond with ONLY "correct" or "incorrect" followed by brief feedback."""

        response = await self._client.messages.create(
            model=self.model,
            max_tokens=50,
            messages=[{"role": "user", "content": prompt}],
        )

        # Extract text from the first text block
        text = ""
        for block in response.content:
            if hasattr(block, "text"):
                text = block.text.lower()
                break

        correct = text.startswith("correct")

        return {
            "correct": correct,
            "feedback": text if not correct else "",
        }
