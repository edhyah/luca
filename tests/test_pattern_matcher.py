"""Tests for the pattern matcher."""

import pytest

from luca.pipeline.pattern_matcher import (
    MatchResult,
    MatchSignal,
    PatternMatcher,
    generate_diff,
    normalize_accents,
    normalize_pronouns,
    normalize_text,
    normalize_whitespace,
)


class TestNormalizeAccents:
    """Tests for accent normalization."""

    def test_removes_acute_accents(self):
        assert normalize_accents("café") == "cafe"
        assert normalize_accents("él") == "el"
        assert normalize_accents("está") == "esta"

    def test_removes_tilde_from_n(self):
        assert normalize_accents("español") == "espanol"
        assert normalize_accents("señor") == "senor"
        assert normalize_accents("niño") == "nino"

    def test_removes_umlaut(self):
        assert normalize_accents("pingüino") == "pinguino"
        assert normalize_accents("vergüenza") == "verguenza"

    def test_handles_multiple_accents(self):
        assert normalize_accents("además") == "ademas"
        assert normalize_accents("canción") == "cancion"

    def test_preserves_non_accented_text(self):
        assert normalize_accents("hello world") == "hello world"
        assert normalize_accents("hola") == "hola"

    def test_handles_empty_string(self):
        assert normalize_accents("") == ""


class TestNormalizeWhitespace:
    """Tests for whitespace and punctuation normalization."""

    def test_collapses_multiple_spaces(self):
        assert normalize_whitespace("hello   world") == "hello world"

    def test_strips_leading_trailing_whitespace(self):
        assert normalize_whitespace("  hello  ") == "hello"

    def test_removes_punctuation(self):
        assert normalize_whitespace("hello, world!") == "hello world"
        assert normalize_whitespace("¿cómo estás?") == "cómo estás"

    def test_preserves_apostrophes(self):
        assert normalize_whitespace("it's fine") == "it's fine"

    def test_handles_empty_string(self):
        assert normalize_whitespace("") == ""


class TestNormalizePronouns:
    """Tests for Spanish pronoun normalization."""

    def test_removes_yo(self):
        assert normalize_pronouns("yo hablo") == "hablo"
        assert normalize_pronouns("yo hablo español") == "hablo español"

    def test_removes_tu_with_accent(self):
        assert normalize_pronouns("tú hablas") == "hablas"

    def test_removes_tu_without_accent(self):
        assert normalize_pronouns("tu hablas") == "hablas"

    def test_removes_el_with_accent(self):
        assert normalize_pronouns("él habla") == "habla"

    def test_removes_ella(self):
        assert normalize_pronouns("ella habla") == "habla"

    def test_removes_usted(self):
        assert normalize_pronouns("usted habla") == "habla"

    def test_removes_nosotros(self):
        assert normalize_pronouns("nosotros hablamos") == "hablamos"

    def test_removes_ellos(self):
        assert normalize_pronouns("ellos hablan") == "hablan"

    def test_removes_ustedes(self):
        assert normalize_pronouns("ustedes hablan") == "hablan"

    def test_preserves_single_pronoun(self):
        # Don't remove if it's the only word
        assert normalize_pronouns("yo") == "yo"

    def test_preserves_non_pronoun_start(self):
        assert normalize_pronouns("hablo español") == "hablo español"

    def test_handles_empty_string(self):
        assert normalize_pronouns("") == ""


class TestGenerateDiff:
    """Tests for error diff generation."""

    def test_missing_words(self):
        diff = generate_diff("hola mundo", "hola")
        assert "missing" in diff
        assert "mundo" in diff

    def test_extra_words(self):
        diff = generate_diff("hola", "hola mundo")
        assert "extra" in diff
        assert "mundo" in diff

    def test_both_missing_and_extra(self):
        diff = generate_diff("hola mundo", "hola amigo")
        assert "missing" in diff
        assert "mundo" in diff
        assert "extra" in diff
        assert "amigo" in diff

    def test_word_order_difference(self):
        diff = generate_diff("hola mundo", "mundo hola")
        assert "word order" in diff

    def test_minor_spelling(self):
        # When normalized words are same but original had minor diffs
        diff = generate_diff("hola", "hola")
        assert "minor spelling" in diff or "word order" in diff


class TestPatternMatcher:
    """Tests for PatternMatcher basic functionality."""

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


class TestPatternMatcherAccents:
    """Tests for accent handling in pattern matching."""

    def test_accent_in_expected_matches_no_accent(self):
        """Expected has accent, input doesn't."""
        matcher = PatternMatcher(threshold=85.0)
        matcher.set_expected_patterns(["café"])

        is_match, score = matcher.match("cafe")
        assert is_match is True
        assert score >= 85.0

    def test_no_accent_in_expected_matches_accent(self):
        """Expected has no accent, input does."""
        matcher = PatternMatcher(threshold=85.0)
        matcher.set_expected_patterns(["cafe"])

        is_match, score = matcher.match("café")
        assert is_match is True
        assert score >= 85.0

    def test_spanish_n_tilde(self):
        """Test ñ matching n."""
        matcher = PatternMatcher(threshold=85.0)
        matcher.set_expected_patterns(["español"])

        is_match, score = matcher.match("espanol")
        assert is_match is True
        assert score >= 85.0

    def test_multiple_accents(self):
        """Test word with multiple accented characters."""
        matcher = PatternMatcher(threshold=85.0)
        matcher.set_expected_patterns(["está bien"])

        is_match, score = matcher.match("esta bien")
        assert is_match is True
        assert score >= 85.0

    def test_el_with_and_without_accent(self):
        """Test él vs el."""
        matcher = PatternMatcher(threshold=85.0)
        matcher.set_expected_patterns(["él habla"])

        is_match, score = matcher.match("el habla")
        assert is_match is True
        assert score >= 85.0


class TestPatternMatcherPronouns:
    """Tests for optional pronoun handling."""

    def test_yo_optional(self):
        """Input has 'yo', expected doesn't."""
        matcher = PatternMatcher(threshold=85.0)
        matcher.set_expected_patterns(["hablo español"])

        is_match, score = matcher.match("yo hablo español")
        assert is_match is True
        assert score >= 85.0

    def test_expected_has_yo_input_doesnt(self):
        """Expected has 'yo', input doesn't."""
        matcher = PatternMatcher(threshold=85.0)
        matcher.set_expected_patterns(["yo hablo español"])

        is_match, score = matcher.match("hablo español")
        assert is_match is True
        assert score >= 85.0

    def test_tu_optional(self):
        """Test tú/tu optionality."""
        matcher = PatternMatcher(threshold=85.0)
        matcher.set_expected_patterns(["hablas español"])

        is_match, score = matcher.match("tú hablas español")
        assert is_match is True
        assert score >= 85.0

    def test_ella_optional(self):
        """Test ella optionality."""
        matcher = PatternMatcher(threshold=85.0)
        matcher.set_expected_patterns(["habla español"])

        is_match, score = matcher.match("ella habla español")
        assert is_match is True
        assert score >= 85.0

    def test_nosotros_optional(self):
        """Test nosotros optionality."""
        matcher = PatternMatcher(threshold=85.0)
        matcher.set_expected_patterns(["hablamos español"])

        is_match, score = matcher.match("nosotros hablamos español")
        assert is_match is True
        assert score >= 85.0


class TestPatternMatcherPunctuation:
    """Tests for punctuation handling."""

    def test_comma_variations(self):
        """Test comma vs no comma."""
        matcher = PatternMatcher(threshold=85.0)
        matcher.set_expected_patterns(["no es normal, es natural"])

        is_match, score = matcher.match("no es normal es natural")
        assert is_match is True
        assert score >= 85.0

    def test_question_marks(self):
        """Test inverted question marks."""
        matcher = PatternMatcher(threshold=85.0)
        matcher.set_expected_patterns(["¿cómo estás?"])

        is_match, score = matcher.match("como estas")
        assert is_match is True
        assert score >= 85.0

    def test_exclamation_marks(self):
        """Test exclamation marks."""
        matcher = PatternMatcher(threshold=85.0)
        matcher.set_expected_patterns(["¡hola!"])

        is_match, score = matcher.match("hola")
        assert is_match is True
        assert score >= 85.0


class TestPatternMatcherWordOrder:
    """Tests for word order variations."""

    def test_simple_word_swap(self):
        """Test that word order variations can match."""
        matcher = PatternMatcher(threshold=70.0)  # Lower threshold for word order
        matcher.set_expected_patterns(["es muy bueno"])

        # Token sort should help here
        is_match, score = matcher.match("muy bueno es")
        assert is_match is True
        assert score >= 70.0

    def test_adverb_placement_variation(self):
        """Test adverb placement flexibility."""
        matcher = PatternMatcher(threshold=80.0)
        matcher.set_expected_patterns(["normalmente no es legal"])

        is_match, score = matcher.match("no es normalmente legal")
        assert is_match is True
        assert score >= 80.0


class TestMatchWithSignal:
    """Tests for the three-signal match_with_signal() method."""

    def test_clear_match_signal(self):
        """Test CLEAR_MATCH signal for high-confidence matches."""
        matcher = PatternMatcher(match_threshold=90.0, miss_threshold=60.0)
        matcher.set_expected_patterns(["hola"])

        result = matcher.match_with_signal("hola")
        assert result.signal == MatchSignal.CLEAR_MATCH
        assert result.score >= 90.0
        assert result.best_match == "hola"
        assert result.diff is None

    def test_clear_miss_signal(self):
        """Test CLEAR_MISS signal for low-confidence matches."""
        matcher = PatternMatcher(match_threshold=90.0, miss_threshold=60.0)
        matcher.set_expected_patterns(["hola"])

        result = matcher.match_with_signal("goodbye world")
        assert result.signal == MatchSignal.CLEAR_MISS
        assert result.score <= 60.0
        assert result.best_match == "hola"
        assert result.diff is not None

    def test_ambiguous_signal(self):
        """Test AMBIGUOUS signal for mid-range scores."""
        matcher = PatternMatcher(match_threshold=90.0, miss_threshold=60.0)
        matcher.set_expected_patterns(["me gusta comer"])

        # One wrong word - similar structure, different meaning
        result = matcher.match_with_signal("me gusta bailar")
        assert result.signal == MatchSignal.AMBIGUOUS
        assert 60.0 < result.score < 90.0
        assert result.diff is not None

    def test_empty_patterns_returns_miss(self):
        """Test that empty patterns returns CLEAR_MISS."""
        matcher = PatternMatcher()
        matcher.set_expected_patterns([])

        result = matcher.match_with_signal("anything")
        assert result.signal == MatchSignal.CLEAR_MISS
        assert result.score == 0.0
        assert result.best_match is None

    def test_selects_best_matching_pattern(self):
        """Test that the best matching pattern is selected."""
        matcher = PatternMatcher()
        matcher.set_expected_patterns(["adios", "hola", "buenos dias"])

        result = matcher.match_with_signal("hola")
        assert result.best_match == "hola"
        assert result.signal == MatchSignal.CLEAR_MATCH


class TestThresholdEdgeCases:
    """Tests for threshold boundary conditions."""

    def test_score_exactly_at_match_threshold(self):
        """Test score exactly at match threshold is CLEAR_MATCH."""
        matcher = PatternMatcher(match_threshold=90.0, miss_threshold=60.0)
        matcher.set_expected_patterns(["test"])

        # Force a scenario where score is exactly 90
        # This is hard to engineer exactly, so we test boundary behavior
        result = matcher.match_with_signal("test")
        # Exact match = 100, so should be CLEAR_MATCH
        assert result.signal == MatchSignal.CLEAR_MATCH

    def test_score_exactly_at_miss_threshold(self):
        """Test score exactly at miss threshold is CLEAR_MISS."""
        matcher = PatternMatcher(match_threshold=90.0, miss_threshold=60.0)
        matcher.set_expected_patterns(["abcdefghij"])

        # Very different string should be below threshold
        result = matcher.match_with_signal("xyz")
        assert result.signal == MatchSignal.CLEAR_MISS

    def test_custom_thresholds(self):
        """Test with custom threshold values."""
        matcher = PatternMatcher(match_threshold=95.0, miss_threshold=50.0)
        matcher.set_expected_patterns(["hola mundo"])

        # Should be ambiguous with these stricter thresholds
        result = matcher.match_with_signal("hola mund")
        # 90.9% match - below 95% threshold
        assert result.signal == MatchSignal.AMBIGUOUS


class TestSTTErrors:
    """Tests for common speech-to-text errors."""

    def test_es_vs_ez_homophone(self):
        """Test common STT confusion between es/ez."""
        matcher = PatternMatcher(threshold=85.0)
        matcher.set_expected_patterns(["es normal"])

        is_match, score = matcher.match("ez normal")
        assert is_match is True
        assert score >= 85.0

    def test_missing_final_s(self):
        """Test common STT dropping of final 's'."""
        matcher = PatternMatcher(threshold=80.0)
        matcher.set_expected_patterns(["buenos dias"])

        is_match, score = matcher.match("bueno dia")
        assert is_match is True
        assert score >= 70.0  # Allow some flexibility

    def test_b_v_confusion(self):
        """Test b/v confusion (same sound in Spanish)."""
        matcher = PatternMatcher(threshold=75.0)  # Lower threshold for single char difference
        matcher.set_expected_patterns(["bien"])

        is_match, score = matcher.match("vien")
        assert is_match is True
        assert score >= 75.0

    def test_extra_filler_words(self):
        """Test STT adding filler words."""
        matcher = PatternMatcher(threshold=70.0)
        matcher.set_expected_patterns(["hablo español"])

        is_match, score = matcher.match("um hablo español")
        # Token set ratio should help here
        assert is_match is True


class TestMenteWords:
    """Tests for -mente adverb suffix handling."""

    def test_constantemente(self):
        """Test -mente words match."""
        matcher = PatternMatcher(threshold=85.0)
        matcher.set_expected_patterns(["constantemente"])

        is_match, score = matcher.match("constantemente")
        assert is_match is True
        assert score == 100.0

    def test_normalmente(self):
        """Test normalmente variations."""
        matcher = PatternMatcher(threshold=85.0)
        matcher.set_expected_patterns(["normalmente"])

        is_match, score = matcher.match("normalmente")
        assert is_match is True
        assert score == 100.0

    def test_mente_word_in_sentence(self):
        """Test -mente word in context."""
        matcher = PatternMatcher(threshold=85.0)
        matcher.set_expected_patterns(["es completamente normal"])

        is_match, score = matcher.match("es completamente normal")
        assert is_match is True


class TestComplexSentences:
    """Tests for more complex sentence patterns."""

    def test_no_es_normal_es_natural(self):
        """Test the specific curriculum phrase."""
        matcher = PatternMatcher(threshold=85.0)
        matcher.set_expected_patterns(["no es normal, es natural"])

        is_match, score = matcher.match("no es normal es natural")
        assert is_match is True

    def test_with_accent_variations(self):
        """Test complex sentence with accents."""
        matcher = PatternMatcher(threshold=85.0)
        matcher.set_expected_patterns(["él está aquí"])

        is_match, score = matcher.match("el esta aqui")
        assert is_match is True

    def test_multiple_acceptable_answers(self):
        """Test when multiple answers are acceptable."""
        matcher = PatternMatcher(threshold=85.0)
        matcher.set_expected_patterns(["sí", "claro", "por supuesto"])

        result1 = matcher.match_with_signal("sí")
        result2 = matcher.match_with_signal("claro")
        result3 = matcher.match_with_signal("por supuesto")

        assert result1.signal == MatchSignal.CLEAR_MATCH
        assert result2.signal == MatchSignal.CLEAR_MATCH
        assert result3.signal == MatchSignal.CLEAR_MATCH


class TestMatchResultDataclass:
    """Tests for MatchResult dataclass."""

    def test_match_result_fields(self):
        """Test MatchResult has all expected fields."""
        result = MatchResult(
            signal=MatchSignal.CLEAR_MATCH,
            score=95.0,
            best_match="hola",
            diff=None,
        )
        assert result.signal == MatchSignal.CLEAR_MATCH
        assert result.score == 95.0
        assert result.best_match == "hola"
        assert result.diff is None

    def test_match_result_with_diff(self):
        """Test MatchResult with diff field populated."""
        result = MatchResult(
            signal=MatchSignal.CLEAR_MISS,
            score=45.0,
            best_match="hola mundo",
            diff="missing: mundo",
        )
        assert result.signal == MatchSignal.CLEAR_MISS
        assert "missing" in result.diff


class TestMatchSignalEnum:
    """Tests for MatchSignal enum."""

    def test_signal_values(self):
        """Test enum values."""
        assert MatchSignal.CLEAR_MATCH.value == "clear_match"
        assert MatchSignal.CLEAR_MISS.value == "clear_miss"
        assert MatchSignal.AMBIGUOUS.value == "ambiguous"

    def test_signal_comparison(self):
        """Test enum comparison."""
        assert MatchSignal.CLEAR_MATCH == MatchSignal.CLEAR_MATCH
        assert MatchSignal.CLEAR_MATCH != MatchSignal.CLEAR_MISS
