"""Tests for the pattern matcher."""

import pytest
from luca.pipeline.pattern_matcher import PatternMatcher


class TestPatternMatcher:
    """Tests for PatternMatcher."""

    def test_exact_match(self):
        """Test exact string matching."""
        matcher = PatternMatcher(threshold=85.0)
        matcher.set_expected_patterns(["hola"])

        is_match, score = matcher.match("hola")
        assert is_match is True
        assert score == 100.0

    def test_fuzzy_match(self):
        """Test fuzzy matching with minor differences."""
        matcher = PatternMatcher(threshold=80.0)
        matcher.set_expected_patterns(["buenos dias"])

        # Close enough match
        is_match, score = matcher.match("buenos dia")
        assert is_match is True
        assert score >= 80.0

    def test_no_match(self):
        """Test that non-matching strings don't match."""
        matcher = PatternMatcher(threshold=85.0)
        matcher.set_expected_patterns(["hola"])

        is_match, score = matcher.match("goodbye")
        assert is_match is False
        assert score < 85.0

    def test_case_insensitive(self):
        """Test that matching is case insensitive."""
        matcher = PatternMatcher(threshold=85.0)
        matcher.set_expected_patterns(["Hola"])

        is_match, score = matcher.match("HOLA")
        assert is_match is True

    def test_multiple_patterns(self):
        """Test matching against multiple patterns."""
        matcher = PatternMatcher(threshold=85.0)
        matcher.set_expected_patterns(["hola", "buenos dias", "buenas tardes"])

        is_match, score = matcher.match("buenos dias")
        assert is_match is True
        assert score == 100.0

    def test_empty_patterns(self):
        """Test with no expected patterns."""
        matcher = PatternMatcher(threshold=85.0)
        matcher.set_expected_patterns([])

        is_match, score = matcher.match("anything")
        assert is_match is False
        assert score == 0.0
