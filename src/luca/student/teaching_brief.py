"""Teaching briefs for personalized instruction."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import google.generativeai as genai

from luca.utils.logging import get_logger

if TYPE_CHECKING:
    from luca.student.error_tracker import ErrorPattern
    from luca.student.triggers import TriggerEvent

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

    # Trigger that caused this brief
    trigger_type: str = ""
    trigger_concept: str = ""

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

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for persistence."""
        return {
            "student_id": self.student_id,
            "strengths": self.strengths,
            "challenges": self.challenges,
            "preferred_explanation_style": self.preferred_explanation_style,
            "optimal_session_length": self.optimal_session_length,
            "response_time_pattern": self.response_time_pattern,
            "error_patterns": self.error_patterns,
            "effective_strategies": self.effective_strategies,
            "summary": self.summary,
            "trigger_type": self.trigger_type,
            "trigger_concept": self.trigger_concept,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TeachingBrief:
        """Create from dictionary."""
        return cls(
            student_id=data["student_id"],
            strengths=data.get("strengths", []),
            challenges=data.get("challenges", []),
            preferred_explanation_style=data.get("preferred_explanation_style", ""),
            optimal_session_length=data.get("optimal_session_length", 20),
            response_time_pattern=data.get("response_time_pattern", "average"),
            error_patterns=data.get("error_patterns", []),
            effective_strategies=data.get("effective_strategies", []),
            summary=data.get("summary", ""),
            trigger_type=data.get("trigger_type", ""),
            trigger_concept=data.get("trigger_concept", ""),
        )


def _build_prompt(
    student_id: str,
    session_history: list[dict[str, Any]],
    error_patterns: list[ErrorPattern],
    mastery_levels: dict[str, float],
    sliding_window_stats: dict[str, Any],
    trigger_event: TriggerEvent | None,
) -> str:
    """Build the prompt for Gemini Flash."""
    prompt_parts = [
        "You are analyzing a language learning session to generate actionable teaching insights.",
        "",
        "## Student Information",
        f"Student ID: {student_id}",
        "",
    ]

    # Add trigger context
    if trigger_event:
        prompt_parts.extend([
            "## Trigger Event",
            f"Type: {trigger_event.trigger_type.value}",
            f"Concept: {trigger_event.concept_id}",
            f"Details: {json.dumps(trigger_event.details)}",
            "",
        ])

    # Add mastery levels
    prompt_parts.append("## Current Mastery Levels")
    for concept_id, mastery in mastery_levels.items():
        prompt_parts.append(f"- {concept_id}: {mastery:.2f}")
    prompt_parts.append("")

    # Add sliding window stats
    prompt_parts.extend([
        "## Recent Performance (Sliding Window)",
        f"- Error rate: {sliding_window_stats.get('error_rate', 0):.2%}",
        f"- Average response time: {sliding_window_stats.get('avg_response_time', 0):.2f}s",
        f"- Current streak: {sliding_window_stats.get('streak_length', 0)} correct",
        f"- Responses in window: {sliding_window_stats.get('response_count', 0)}",
        "",
    ])

    # Add error patterns
    if error_patterns:
        prompt_parts.append("## Repeated Error Patterns")
        for pattern in error_patterns:
            prompt_parts.append(f"- {pattern.error_type} on {pattern.concept_id}: {pattern.count} occurrences")
            if pattern.occurrences:
                last = pattern.occurrences[-1]
                prompt_parts.append(f"  Last: student said '{last.student_response}', expected '{last.expected_response}'")
        prompt_parts.append("")

    # Add session history (last 20 exchanges)
    recent_history = session_history[-20:] if len(session_history) > 20 else session_history
    if recent_history:
        prompt_parts.append("## Recent Session History")
        for i, exchange in enumerate(recent_history):
            correct = "correct" if exchange.get("correct") else "incorrect"
            concept = exchange.get("concept_id", "unknown")
            time_ms = exchange.get("response_time")
            time_str = f" ({time_ms/1000:.1f}s)" if time_ms else ""
            prompt_parts.append(f"{i+1}. [{concept}] {correct}{time_str}")
        prompt_parts.append("")

    # Add response format
    prompt_parts.extend([
        "## Your Task",
        "Generate a teaching brief with actionable insights. Respond with valid JSON only:",
        "",
        "```json",
        "{",
        '  "strengths": ["list of 1-3 specific strengths observed"],',
        '  "challenges": ["list of 1-3 specific challenges to address"],',
        '  "error_patterns": ["list of specific error patterns to watch for"],',
        '  "effective_strategies": ["list of 1-3 teaching strategies that would help"],',
        '  "preferred_explanation_style": "brief description of how to explain things",',
        '  "summary": "2-3 sentence actionable summary for the tutor"',
        "}",
        "```",
        "",
        "Focus on actionable, specific insights. Be concise.",
    ])

    return "\n".join(prompt_parts)


def _parse_response(response_text: str, student_id: str, trigger_event: TriggerEvent | None) -> TeachingBrief:
    """Parse Gemini response into TeachingBrief."""
    # Extract JSON from response
    try:
        # Try to find JSON block
        if "```json" in response_text:
            json_start = response_text.index("```json") + 7
            json_end = response_text.index("```", json_start)
            json_str = response_text[json_start:json_end].strip()
        elif "```" in response_text:
            json_start = response_text.index("```") + 3
            json_end = response_text.index("```", json_start)
            json_str = response_text[json_start:json_end].strip()
        else:
            # Try to parse entire response as JSON
            json_str = response_text.strip()

        data = json.loads(json_str)

        return TeachingBrief(
            student_id=student_id,
            strengths=data.get("strengths", []),
            challenges=data.get("challenges", []),
            preferred_explanation_style=data.get("preferred_explanation_style", ""),
            error_patterns=data.get("error_patterns", []),
            effective_strategies=data.get("effective_strategies", []),
            summary=data.get("summary", ""),
            trigger_type=trigger_event.trigger_type.value if trigger_event else "",
            trigger_concept=trigger_event.concept_id if trigger_event else "",
        )
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"Failed to parse Gemini response: {e}")
        # Return a basic brief with the raw summary
        return TeachingBrief(
            student_id=student_id,
            summary=response_text[:500] if response_text else "Analysis unavailable",
            trigger_type=trigger_event.trigger_type.value if trigger_event else "",
            trigger_concept=trigger_event.concept_id if trigger_event else "",
        )


async def generate_teaching_brief(
    student_id: str,
    session_history: list[dict[str, Any]],
    error_patterns: list[ErrorPattern] | None = None,
    mastery_levels: dict[str, float] | None = None,
    sliding_window_stats: dict[str, Any] | None = None,
    trigger_event: TriggerEvent | None = None,
) -> TeachingBrief:
    """Generate a teaching brief from session history using Gemini Flash.

    Args:
        student_id: The student's ID.
        session_history: List of session exchanges with concept_id, correct, response_time.
        error_patterns: List of ErrorPattern objects from the ErrorTracker.
        mastery_levels: Dict mapping concept_id to mastery probability.
        sliding_window_stats: Dict with error_rate, avg_response_time, streak_length, response_count.
        trigger_event: The TriggerEvent that caused this brief generation.

    Returns:
        A TeachingBrief with actionable insights.
    """
    logger.info(f"Generating teaching brief for student {student_id}")

    # Use defaults for missing data
    error_patterns = error_patterns or []
    mastery_levels = mastery_levels or {}
    sliding_window_stats = sliding_window_stats or {}

    # Build prompt
    prompt = _build_prompt(
        student_id=student_id,
        session_history=session_history,
        error_patterns=error_patterns,
        mastery_levels=mastery_levels,
        sliding_window_stats=sliding_window_stats,
        trigger_event=trigger_event,
    )

    # Check for API key
    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        logger.warning("No Gemini API key found, returning empty brief")
        return TeachingBrief(
            student_id=student_id,
            summary="Teaching brief generation unavailable (no API key)",
            trigger_type=trigger_event.trigger_type.value if trigger_event else "",
            trigger_concept=trigger_event.concept_id if trigger_event else "",
        )

    try:
        # Configure Gemini
        genai.configure(api_key=api_key)  # type: ignore[attr-defined]
        model = genai.GenerativeModel("gemini-1.5-flash")  # type: ignore[attr-defined]

        # Generate response
        response = await model.generate_content_async(
            prompt,
            generation_config=genai.GenerationConfig(  # type: ignore[attr-defined]
                temperature=0.3,
                max_output_tokens=1024,
            ),
        )

        if not response.text:
            logger.warning("Empty response from Gemini")
            return TeachingBrief(
                student_id=student_id,
                summary="Analysis returned empty response",
                trigger_type=trigger_event.trigger_type.value if trigger_event else "",
                trigger_concept=trigger_event.concept_id if trigger_event else "",
            )

        # Parse response
        brief = _parse_response(response.text, student_id, trigger_event)
        logger.info(f"Generated teaching brief with {len(brief.effective_strategies)} strategies")
        return brief

    except Exception as e:
        logger.error(f"Error generating teaching brief: {e}")
        return TeachingBrief(
            student_id=student_id,
            summary=f"Analysis failed: {e}",
            trigger_type=trigger_event.trigger_type.value if trigger_event else "",
            trigger_concept=trigger_event.concept_id if trigger_event else "",
        )
