"""Tier 1 fuzzy pattern matching for common student responses."""

from pipecat.frames.frames import Frame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from rapidfuzz import fuzz

from luca.utils.logging import get_logger

logger = get_logger("pipeline.pattern_matcher")


class PatternMatcher(FrameProcessor):
    """Fast fuzzy matching for expected student responses."""

    def __init__(self, threshold: float = 85.0) -> None:
        super().__init__()
        self.threshold = threshold
        self.expected_patterns: list[str] = []

    def set_expected_patterns(self, patterns: list[str]) -> None:
        """Set the expected response patterns for the current prompt."""
        self.expected_patterns = patterns

    def match(self, text: str) -> tuple[bool, float]:
        """Check if text matches any expected pattern."""
        if not self.expected_patterns:
            return False, 0.0

        best_score = 0.0
        for pattern in self.expected_patterns:
            score = fuzz.ratio(text.lower(), pattern.lower())
            best_score = max(best_score, score)

        return best_score >= self.threshold, best_score

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        """Process frames and check for pattern matches."""
        # TODO: Implement pattern matching on transcription frames
        await self.push_frame(frame, direction)
