"""Tier 1 fuzzy pattern matching for common student responses."""

import re
import unicodedata
from dataclasses import dataclass
from enum import Enum

from pipecat.frames.frames import Frame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from rapidfuzz import fuzz

from luca.utils.logging import get_logger

logger = get_logger("pipeline.pattern_matcher")


class MatchSignal(Enum):
    """Three-signal output for pattern matching."""

    CLEAR_MATCH = "clear_match"
    CLEAR_MISS = "clear_miss"
    AMBIGUOUS = "ambiguous"


@dataclass
class MatchResult:
    """Result of a pattern match attempt."""

    signal: MatchSignal
    score: float
    best_match: str | None  # Which expected answer was closest
    diff: str | None  # For CLEAR_MISS: what's wrong


# Spanish subject pronouns that can be optionally dropped
SPANISH_SUBJECT_PRONOUNS = frozenset(
    {
        "yo",
        "tú",
        "tu",  # without accent (common in STT)
        "él",
        "el",  # without accent
        "ella",
        "usted",
        "nosotros",
        "nosotras",
        "vosotros",
        "vosotras",
        "ellos",
        "ellas",
        "ustedes",
    }
)


def normalize_accents(text: str) -> str:
    """Normalize accented characters for comparison.

    Converts accented characters to their base form (é→e, ñ→n, etc.)
    while preserving the original text structure.
    """
    # Normalize to NFD (decomposed form), then remove combining marks
    normalized = unicodedata.normalize("NFD", text)
    # Remove combining diacritical marks (accents, tildes, etc.)
    return "".join(c for c in normalized if unicodedata.category(c) != "Mn")


def normalize_whitespace(text: str) -> str:
    """Normalize whitespace and remove punctuation for comparison."""
    # Remove punctuation except apostrophes (for contractions)
    text = re.sub(r"[^\w\s']", " ", text)
    # Collapse multiple spaces
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_pronouns(text: str) -> str:
    """Remove optional Spanish subject pronouns from the beginning.

    In Spanish, subject pronouns are often optional since the verb
    conjugation indicates the subject. This allows "yo hablo" to match "hablo".
    """
    words = text.split()
    if not words:
        return text

    # Check if first word is a subject pronoun
    first_word_normalized = normalize_accents(words[0].lower())
    if first_word_normalized in SPANISH_SUBJECT_PRONOUNS and len(words) > 1:
        return " ".join(words[1:])

    return text


def normalize_text(text: str) -> str:
    """Apply all normalizations to text for comparison."""
    text = text.lower()
    text = normalize_whitespace(text)
    text = normalize_accents(text)
    return text


def normalize_text_with_pronouns(text: str) -> str:
    """Apply all normalizations including pronoun removal."""
    text = text.lower()
    text = normalize_whitespace(text)
    text = normalize_pronouns(text)
    text = normalize_accents(text)
    return text


def generate_diff(expected: str, actual: str) -> str:
    """Generate a human-readable diff between expected and actual text.

    Returns a string describing what's wrong with the actual text.
    """
    expected_words = normalize_text(expected).split()
    actual_words = normalize_text(actual).split()

    expected_set = set(expected_words)
    actual_set = set(actual_words)

    missing = expected_set - actual_set
    extra = actual_set - expected_set

    parts = []

    if missing:
        parts.append(f"missing: {', '.join(sorted(missing))}")

    if extra:
        parts.append(f"extra: {', '.join(sorted(extra))}")

    if not parts:
        # Words are the same but order might be different
        if expected_words != actual_words:
            parts.append("word order differs")
        else:
            parts.append("minor spelling differences")

    return "; ".join(parts)


class PatternMatcher(FrameProcessor):
    """Fast fuzzy matching for expected student responses.

    Supports Spanish-specific handling including:
    - Accent normalization (café matches cafe)
    - Optional subject pronoun handling (yo hablo matches hablo)
    - Three-signal output (CLEAR_MATCH, CLEAR_MISS, AMBIGUOUS)
    - Error diff reporting for misses
    """

    def __init__(
        self,
        threshold: float = 85.0,
        match_threshold: float = 90.0,
        miss_threshold: float = 60.0,
    ) -> None:
        """Initialize the pattern matcher.

        Args:
            threshold: Legacy threshold for simple match() method.
            match_threshold: Score >= this is CLEAR_MATCH (default 90.0).
            miss_threshold: Score <= this is CLEAR_MISS (default 60.0).
                           Scores between miss_threshold and match_threshold are AMBIGUOUS.
        """
        super().__init__()
        self.threshold = threshold
        self.match_threshold = match_threshold
        self.miss_threshold = miss_threshold
        self.expected_patterns: list[str] = []

    def set_expected_patterns(self, patterns: list[str]) -> None:
        """Set the expected response patterns for the current prompt."""
        self.expected_patterns = patterns

    def _compute_score(self, text: str, pattern: str) -> float:
        """Compute the best match score between text and pattern.

        Tries multiple normalization strategies and returns the highest score.
        """
        scores = []

        # Strategy 1: Basic normalization (case + whitespace + accents)
        text_norm = normalize_text(text)
        pattern_norm = normalize_text(pattern)
        scores.append(fuzz.ratio(text_norm, pattern_norm))

        # Strategy 2: With pronoun removal from input
        text_with_pronoun_removal = normalize_text_with_pronouns(text)
        scores.append(fuzz.ratio(text_with_pronoun_removal, pattern_norm))

        # Strategy 3: With pronoun removal from pattern (in case pattern has pronoun)
        pattern_with_pronoun_removal = normalize_text_with_pronouns(pattern)
        scores.append(fuzz.ratio(text_norm, pattern_with_pronoun_removal))

        # Strategy 4: Both with pronoun removal
        scores.append(
            fuzz.ratio(text_with_pronoun_removal, pattern_with_pronoun_removal)
        )

        # Strategy 5: Token sort ratio (handles word order variations)
        scores.append(fuzz.token_sort_ratio(text_norm, pattern_norm))

        # Strategy 6: Token set ratio (handles extra/missing words)
        scores.append(fuzz.token_set_ratio(text_norm, pattern_norm))

        return max(scores)

    def match(self, text: str) -> tuple[bool, float]:
        """Check if text matches any expected pattern.

        This is the legacy method that returns a simple boolean match.
        For richer output, use match_with_signal() instead.
        """
        if not self.expected_patterns:
            return False, 0.0

        best_score = 0.0
        for pattern in self.expected_patterns:
            score = self._compute_score(text, pattern)
            best_score = max(best_score, score)

        return best_score >= self.threshold, best_score

    def match_with_signal(self, text: str) -> MatchResult:
        """Check if text matches any expected pattern with three-signal output.

        Returns a MatchResult with:
        - signal: CLEAR_MATCH, CLEAR_MISS, or AMBIGUOUS
        - score: The best match score (0-100)
        - best_match: Which expected answer was closest
        - diff: For CLEAR_MISS, what's wrong with the answer
        """
        if not self.expected_patterns:
            return MatchResult(
                signal=MatchSignal.CLEAR_MISS,
                score=0.0,
                best_match=None,
                diff="no expected patterns set",
            )

        best_score = 0.0
        best_pattern = self.expected_patterns[0]

        for pattern in self.expected_patterns:
            score = self._compute_score(text, pattern)
            if score > best_score:
                best_score = score
                best_pattern = pattern

        # Determine signal based on thresholds
        if best_score >= self.match_threshold:
            signal = MatchSignal.CLEAR_MATCH
            diff = None
        elif best_score <= self.miss_threshold:
            signal = MatchSignal.CLEAR_MISS
            diff = generate_diff(best_pattern, text)
        else:
            signal = MatchSignal.AMBIGUOUS
            diff = generate_diff(best_pattern, text)

        return MatchResult(
            signal=signal,
            score=best_score,
            best_match=best_pattern,
            diff=diff,
        )

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        """Process frames and check for pattern matches."""
        # TODO: Implement pattern matching on transcription frames
        await self.push_frame(frame, direction)
