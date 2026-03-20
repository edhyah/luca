"""Off-script request detection for meta-commands during tutoring.

Detects when students make meta-requests like asking for repetition,
help, or expressing confusion, bypassing normal pattern evaluation.
"""

import re
from enum import Enum

from luca.utils.logging import get_logger

logger = get_logger("pipeline.off_script")


class OffScriptType(Enum):
    """Types of off-script requests that bypass normal evaluation."""

    REPEAT = "repeat"  # "Can you repeat that?" / "What did you say?"
    SLOW_DOWN = "slow_down"  # "Can you slow down?" / "Too fast"
    CONFUSION = "confusion"  # "I don't understand" / "I'm confused"
    HELP = "help"  # "Help" / "Give me a hint" / "I need help"
    SKIP = "skip"  # "Skip this" / "Move on" / "Next"
    NONE = "none"  # Not an off-script request


class OffScriptDetector:
    """Regex-based detection of meta-requests that bypass normal evaluation.

    These requests should be handled specially by the orchestrator rather than
    being passed through pattern matching and LLM evaluation.
    """

    # Patterns are compiled for efficiency and tested in order of specificity
    PATTERNS: list[tuple[OffScriptType, re.Pattern[str]]] = [
        # REPEAT - requests for repetition
        (
            OffScriptType.REPEAT,
            re.compile(
                r"\b("
                r"repeat|say\s+that\s+again|what\s+did\s+you\s+say|"
                r"come\s+again|pardon|sorry\s+what|huh\??|"
                r"can\s+you\s+(please\s+)?repeat|one\s+more\s+time|"
                r"again\s*\??"
                r")\b",
                re.IGNORECASE,
            ),
        ),
        # SLOW_DOWN - requests to slow down
        (
            OffScriptType.SLOW_DOWN,
            re.compile(
                r"\b("
                r"slow\s*down|too\s+fast|go\s+slower|"
                r"can\s+you\s+(please\s+)?slow|more\s+slowly|"
                r"not\s+so\s+fast"
                r")\b",
                re.IGNORECASE,
            ),
        ),
        # CONFUSION - expressions of confusion
        (
            OffScriptType.CONFUSION,
            re.compile(
                r"\b("
                r"i\s+don'?t\s+understand|i'?m\s+(so\s+)?confused|"
                r"what\s+do\s+you\s+mean|i\s+don'?t\s+get\s+it|"
                r"makes?\s+no\s+sense|lost\s+me|"
                r"i\s+have\s+no\s+idea|no\s+clue"
                r")\b",
                re.IGNORECASE,
            ),
        ),
        # HELP - explicit requests for help
        (
            OffScriptType.HELP,
            re.compile(
                r"\b("
                r"help(\s+me)?|give\s+(me\s+)?a\s+hint|"
                r"i\s+need\s+(a\s+)?hint|hint\s*(please)?|"
                r"can\s+(i\s+)?(have|get)\s+(a\s+)?hint|"
                r"i\s+need\s+help|i'?m\s+stuck"
                r")\b",
                re.IGNORECASE,
            ),
        ),
        # SKIP - requests to skip or move on
        (
            OffScriptType.SKIP,
            re.compile(
                r"\b("
                r"skip(\s+this)?|move\s+on|next(\s+one)?|"
                r"let'?s\s+move\s+on|go\s+to\s+(the\s+)?next|"
                r"i\s+give\s+up|just\s+tell\s+me|"
                r"show\s+me(\s+the\s+answer)?"
                r")\b",
                re.IGNORECASE,
            ),
        ),
    ]

    def detect(self, transcript: str) -> OffScriptType:
        """Detect if transcript is an off-script request.

        Args:
            transcript: The student's transcribed speech.

        Returns:
            OffScriptType indicating the type of meta-request, or NONE if
            the transcript is a normal response that should be evaluated.
        """
        if not transcript or not transcript.strip():
            return OffScriptType.NONE

        # Clean up transcript for matching
        text = transcript.strip()

        # Check each pattern in order
        for off_script_type, pattern in self.PATTERNS:
            if pattern.search(text):
                logger.debug(f"Detected off-script request: {off_script_type.value}")
                return off_script_type

        return OffScriptType.NONE

    def is_off_script(self, transcript: str) -> bool:
        """Check if transcript is any type of off-script request.

        Args:
            transcript: The student's transcribed speech.

        Returns:
            True if the transcript is an off-script request.
        """
        return self.detect(transcript) != OffScriptType.NONE
