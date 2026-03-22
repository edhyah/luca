"""Tests for streaming TTS chunker."""

import time
from unittest.mock import AsyncMock, patch

import pytest
from pipecat.frames.frames import (
    Frame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
    TextFrame,
)
from pipecat.processors.frame_processor import FrameDirection

from luca.pipeline.streaming_tts import StreamingTTSChunker


class TestExtractSentences:
    """Tests for sentence/clause extraction logic."""

    def test_basic_sentences(self):
        """Split on periods."""
        chunker = StreamingTTSChunker()
        sentences, remaining = chunker.extract_sentences("Hello world. How are you.")
        assert sentences == ["Hello world.", "How are you."]
        assert remaining == ""

    def test_question_and_exclamation(self):
        """Split on question marks and exclamation points."""
        chunker = StreamingTTSChunker()
        sentences, remaining = chunker.extract_sentences("What is this? It is great!")
        assert sentences == ["What is this?", "It is great!"]
        assert remaining == ""

    def test_mixed_punctuation(self):
        """Handle mixed sentence endings."""
        chunker = StreamingTTSChunker()
        # Short sentences stay in buffer due to MIN_CHUNK_SIZE
        sentences, remaining = chunker.extract_sentences("Hello. What? Yes!")
        # All are under 10 chars, so they stay buffered
        assert sentences == []
        assert remaining == "Hello. What? Yes!"

    def test_mixed_punctuation_long(self):
        """Handle mixed sentence endings with longer sentences."""
        chunker = StreamingTTSChunker()
        sentences, remaining = chunker.extract_sentences(
            "Hello there. What do you think? Yes indeed!"
        )
        assert sentences == ["Hello there.", "What do you think?", "Yes indeed!"]
        assert remaining == ""

    def test_comma_and_conjunction(self):
        """Split on comma + conjunction."""
        chunker = StreamingTTSChunker()
        sentences, remaining = chunker.extract_sentences(
            "I speak Spanish, and you listen carefully."
        )
        assert sentences == ["I speak Spanish,", "and you listen carefully."]
        assert remaining == ""

    def test_comma_but_conjunction(self):
        """Split on comma + but."""
        chunker = StreamingTTSChunker()
        sentences, remaining = chunker.extract_sentences(
            "I tried hard, but it was difficult."
        )
        assert sentences == ["I tried hard,", "but it was difficult."]
        assert remaining == ""

    def test_comma_so_conjunction(self):
        """Split on comma + so."""
        chunker = StreamingTTSChunker()
        sentences, remaining = chunker.extract_sentences(
            "The answer was correct, so we moved on."
        )
        assert sentences == ["The answer was correct,", "so we moved on."]
        assert remaining == ""

    def test_comma_or_conjunction(self):
        """Split on comma + or."""
        chunker = StreamingTTSChunker()
        sentences, remaining = chunker.extract_sentences(
            "Say hola here, or try another word."
        )
        assert sentences == ["Say hola here,", "or try another word."]
        assert remaining == ""

    def test_comma_yet_conjunction(self):
        """Split on comma + yet."""
        chunker = StreamingTTSChunker()
        sentences, remaining = chunker.extract_sentences(
            "It seemed easy, yet I struggled."
        )
        assert sentences == ["It seemed easy,", "yet I struggled."]
        assert remaining == ""

    def test_case_insensitive_conjunction(self):
        """Conjunctions are case-insensitive."""
        chunker = StreamingTTSChunker()
        sentences, remaining = chunker.extract_sentences(
            "First clause, AND second clause."
        )
        assert sentences == ["First clause,", "AND second clause."]
        assert remaining == ""

    def test_mixed_sentences_and_clauses(self):
        """Handle mix of sentence endings and clause breaks."""
        chunker = StreamingTTSChunker()
        # "Good job!" is only 9 chars, below MIN_CHUNK_SIZE
        sentences, remaining = chunker.extract_sentences(
            "Good job! Now try this, and see what happens."
        )
        # First chunk is too short, so all stays in buffer until longer
        assert sentences == []
        assert remaining == "Good job! Now try this, and see what happens."

    def test_mixed_sentences_and_clauses_long(self):
        """Handle mix of sentence endings and clause breaks with longer text."""
        chunker = StreamingTTSChunker()
        sentences, remaining = chunker.extract_sentences(
            "Excellent work! Now please try this example, and see what happens."
        )
        assert sentences == [
            "Excellent work!",
            "Now please try this example,",
            "and see what happens.",
        ]
        assert remaining == ""

    def test_incomplete_sentence(self):
        """Incomplete text stays in buffer."""
        chunker = StreamingTTSChunker()
        sentences, remaining = chunker.extract_sentences("Hello wor")
        assert sentences == []
        assert remaining == "Hello wor"

    def test_incomplete_with_complete(self):
        """Extract complete sentences, keep incomplete in buffer."""
        chunker = StreamingTTSChunker()
        sentences, remaining = chunker.extract_sentences("First sentence. Second sen")
        assert sentences == ["First sentence."]
        assert remaining == "Second sen"

    def test_empty_string(self):
        """Handle empty input."""
        chunker = StreamingTTSChunker()
        sentences, remaining = chunker.extract_sentences("")
        assert sentences == []
        assert remaining == ""

    def test_whitespace_only(self):
        """Handle whitespace-only input."""
        chunker = StreamingTTSChunker()
        sentences, remaining = chunker.extract_sentences("   ")
        assert sentences == []
        assert remaining == "   "

    def test_multiple_punctuation(self):
        """Handle multiple punctuation marks."""
        chunker = StreamingTTSChunker()
        # Short sentences stay in buffer due to MIN_CHUNK_SIZE
        sentences, remaining = chunker.extract_sentences("What?! Really?!")
        assert sentences == []
        assert remaining == "What?! Really?!"

    def test_multiple_punctuation_long(self):
        """Handle multiple punctuation marks with longer sentences."""
        chunker = StreamingTTSChunker()
        sentences, remaining = chunker.extract_sentences(
            "What is happening?! That is incredible!"
        )
        assert sentences == ["What is happening?!", "That is incredible!"]
        assert remaining == ""

    def test_min_chunk_size_filters_short(self):
        """Chunks shorter than MIN_CHUNK_SIZE stay in buffer."""
        chunker = StreamingTTSChunker()
        # "Hi." is only 3 chars, below MIN_CHUNK_SIZE of 10
        sentences, remaining = chunker.extract_sentences("Hi. There.")
        # "Hi." is too short, so it stays, but "There." gets appended
        # Actually both together get processed - let's check behavior
        assert remaining == "Hi. There."
        assert sentences == []

    def test_chunk_at_min_size(self):
        """Chunks at exactly MIN_CHUNK_SIZE are emitted."""
        chunker = StreamingTTSChunker()
        # Create a sentence that's exactly 10 chars including period
        sentences, remaining = chunker.extract_sentences("123456789. Next.")
        assert sentences == ["123456789."]
        # "Next." is 5 chars, too short
        assert remaining == "Next."


class TestProcessFrame:
    """Tests for frame processing logic."""

    @pytest.fixture
    def chunker(self):
        """Create a chunker with mocked push_frame."""
        chunker = StreamingTTSChunker()
        chunker.push_frame = AsyncMock()
        chunker._pipeline_started = True  # Simulate pipeline started state
        return chunker

    @pytest.mark.asyncio
    async def test_start_frame_resets_buffer(self, chunker):
        """LLMFullResponseStartFrame clears the buffer."""
        chunker._buffer = "leftover text"
        frame = LLMFullResponseStartFrame()

        await chunker.process_frame(frame, FrameDirection.DOWNSTREAM)

        assert chunker._buffer == ""
        chunker.push_frame.assert_called_once_with(frame, FrameDirection.DOWNSTREAM)

    @pytest.mark.asyncio
    async def test_text_frame_buffers_and_emits(self, chunker):
        """LLMTextFrame accumulates text and emits complete sentences."""
        start_frame = LLMFullResponseStartFrame()
        await chunker.process_frame(start_frame, FrameDirection.DOWNSTREAM)
        chunker.push_frame.reset_mock()

        # Send a complete sentence
        text_frame = LLMTextFrame(text="Hello world. ")
        await chunker.process_frame(text_frame, FrameDirection.DOWNSTREAM)

        # Should emit a TextFrame with the sentence
        calls = chunker.push_frame.call_args_list
        assert len(calls) == 1
        emitted_frame = calls[0][0][0]
        assert isinstance(emitted_frame, TextFrame)
        assert emitted_frame.text == "Hello world."

    @pytest.mark.asyncio
    async def test_text_frame_accumulates_incomplete(self, chunker):
        """Incomplete text stays in buffer."""
        start_frame = LLMFullResponseStartFrame()
        await chunker.process_frame(start_frame, FrameDirection.DOWNSTREAM)
        chunker.push_frame.reset_mock()

        # Send incomplete text
        text_frame = LLMTextFrame(text="Hello wor")
        await chunker.process_frame(text_frame, FrameDirection.DOWNSTREAM)

        # Nothing should be emitted
        chunker.push_frame.assert_not_called()
        assert chunker._buffer == "Hello wor"

    @pytest.mark.asyncio
    async def test_streaming_accumulation(self, chunker):
        """Multiple text frames accumulate until sentence complete."""
        start_frame = LLMFullResponseStartFrame()
        await chunker.process_frame(start_frame, FrameDirection.DOWNSTREAM)
        chunker.push_frame.reset_mock()

        # Stream tokens
        await chunker.process_frame(
            LLMTextFrame(text="Hello "), FrameDirection.DOWNSTREAM
        )
        await chunker.process_frame(
            LLMTextFrame(text="world"), FrameDirection.DOWNSTREAM
        )
        await chunker.process_frame(
            LLMTextFrame(text=". "), FrameDirection.DOWNSTREAM
        )

        # Should emit one TextFrame
        calls = chunker.push_frame.call_args_list
        assert len(calls) == 1
        assert calls[0][0][0].text == "Hello world."

    @pytest.mark.asyncio
    async def test_end_frame_flushes_buffer(self, chunker):
        """LLMFullResponseEndFrame flushes remaining buffer."""
        start_frame = LLMFullResponseStartFrame()
        await chunker.process_frame(start_frame, FrameDirection.DOWNSTREAM)
        chunker.push_frame.reset_mock()

        # Send incomplete text
        text_frame = LLMTextFrame(text="Final words")
        await chunker.process_frame(text_frame, FrameDirection.DOWNSTREAM)

        # Send end frame
        end_frame = LLMFullResponseEndFrame()
        await chunker.process_frame(end_frame, FrameDirection.DOWNSTREAM)

        # Should emit the remaining text and then the end frame
        calls = chunker.push_frame.call_args_list
        assert len(calls) == 2
        assert isinstance(calls[0][0][0], TextFrame)
        assert calls[0][0][0].text == "Final words"
        assert calls[1][0][0] is end_frame

    @pytest.mark.asyncio
    async def test_end_frame_empty_buffer(self, chunker):
        """LLMFullResponseEndFrame with empty buffer just passes through."""
        start_frame = LLMFullResponseStartFrame()
        await chunker.process_frame(start_frame, FrameDirection.DOWNSTREAM)

        # Complete sentence
        text_frame = LLMTextFrame(text="Complete sentence. ")
        await chunker.process_frame(text_frame, FrameDirection.DOWNSTREAM)
        chunker.push_frame.reset_mock()

        # Buffer should be empty now, send end frame
        end_frame = LLMFullResponseEndFrame()
        await chunker.process_frame(end_frame, FrameDirection.DOWNSTREAM)

        # Should only emit the end frame
        calls = chunker.push_frame.call_args_list
        assert len(calls) == 1
        assert calls[0][0][0] is end_frame

    @pytest.mark.asyncio
    async def test_other_frames_pass_through(self, chunker):
        """Non-LLM frames pass through unchanged."""
        # Create a generic frame
        other_frame = Frame()

        await chunker.process_frame(other_frame, FrameDirection.DOWNSTREAM)

        chunker.push_frame.assert_called_once_with(other_frame, FrameDirection.DOWNSTREAM)

    @pytest.mark.asyncio
    async def test_upstream_direction_preserved(self, chunker):
        """Frame direction is preserved when pushing frames."""
        frame = LLMFullResponseStartFrame()

        await chunker.process_frame(frame, FrameDirection.UPSTREAM)

        chunker.push_frame.assert_called_once_with(frame, FrameDirection.UPSTREAM)


class TestTimingInstrumentation:
    """Tests for latency tracking."""

    @pytest.fixture
    def chunker(self):
        """Create a chunker with mocked push_frame."""
        chunker = StreamingTTSChunker()
        chunker.push_frame = AsyncMock()
        chunker._pipeline_started = True  # Simulate pipeline started state
        return chunker

    @pytest.mark.asyncio
    async def test_first_token_time_tracked(self, chunker):
        """First token time is recorded on first LLMTextFrame."""
        start_frame = LLMFullResponseStartFrame()
        await chunker.process_frame(start_frame, FrameDirection.DOWNSTREAM)

        assert chunker._first_token_time is None

        text_frame = LLMTextFrame(text="Hello")
        await chunker.process_frame(text_frame, FrameDirection.DOWNSTREAM)

        assert chunker._first_token_time is not None

    @pytest.mark.asyncio
    async def test_first_emit_time_tracked(self, chunker):
        """First emit time is recorded when first sentence emitted."""
        start_frame = LLMFullResponseStartFrame()
        await chunker.process_frame(start_frame, FrameDirection.DOWNSTREAM)

        assert chunker._first_emit_time is None

        # Send a complete sentence
        text_frame = LLMTextFrame(text="Hello world. ")
        await chunker.process_frame(text_frame, FrameDirection.DOWNSTREAM)

        assert chunker._first_emit_time is not None

    @pytest.mark.asyncio
    async def test_timing_reset_on_new_response(self, chunker):
        """Timing is reset when new response starts."""
        # First response
        await chunker.process_frame(
            LLMFullResponseStartFrame(), FrameDirection.DOWNSTREAM
        )
        await chunker.process_frame(
            LLMTextFrame(text="First response. "), FrameDirection.DOWNSTREAM
        )

        assert chunker._first_token_time is not None
        assert chunker._first_emit_time is not None

        # New response
        await chunker.process_frame(
            LLMFullResponseStartFrame(), FrameDirection.DOWNSTREAM
        )

        assert chunker._first_token_time is None
        assert chunker._first_emit_time is None

    @pytest.mark.asyncio
    async def test_latency_logged(self, chunker):
        """Latency is logged when first chunk emitted."""
        with patch("luca.pipeline.streaming_tts.logger") as mock_logger:
            await chunker.process_frame(
                LLMFullResponseStartFrame(), FrameDirection.DOWNSTREAM
            )
            await chunker.process_frame(
                LLMTextFrame(text="Hello world. "), FrameDirection.DOWNSTREAM
            )

            mock_logger.debug.assert_called()
            call_args = mock_logger.debug.call_args
            assert "latency" in call_args[0][0].lower()


class TestIntegration:
    """Integration tests simulating realistic streaming scenarios."""

    @pytest.fixture
    def chunker(self):
        """Create a chunker with mocked push_frame."""
        chunker = StreamingTTSChunker()
        chunker.push_frame = AsyncMock()
        chunker._pipeline_started = True  # Simulate pipeline started state
        return chunker

    @pytest.mark.asyncio
    async def test_full_conversation_flow(self, chunker):
        """Simulate a complete LLM response with streaming tokens."""
        # Start response
        await chunker.process_frame(
            LLMFullResponseStartFrame(), FrameDirection.DOWNSTREAM
        )
        chunker.push_frame.reset_mock()

        # Simulate streaming tokens (like real LLM output)
        # Using longer phrases to ensure they meet MIN_CHUNK_SIZE
        tokens = [
            "Hello there",
            "!",
            " ",
            "Let",
            "'s",
            " practice",
            " some",
            " Spanish",
            " vocabulary",
            ",",
            " and",
            " we",
            " can",
            " start",
            " with",
            " common",
            " greetings",
            ".",
        ]

        emitted = []
        for token in tokens:
            await chunker.process_frame(
                LLMTextFrame(text=token), FrameDirection.DOWNSTREAM
            )
            for call in chunker.push_frame.call_args_list:
                frame = call[0][0]
                if isinstance(frame, TextFrame):
                    emitted.append(frame.text)
            chunker.push_frame.reset_mock()

        # End response - should flush any remaining buffer
        await chunker.process_frame(
            LLMFullResponseEndFrame(), FrameDirection.DOWNSTREAM
        )
        for call in chunker.push_frame.call_args_list:
            frame = call[0][0]
            if isinstance(frame, TextFrame):
                emitted.append(frame.text)

        # Check we got chunks
        assert len(emitted) >= 1
        # All text should be accounted for
        full_text = " ".join(emitted)
        assert "Hello" in full_text
        assert "Spanish" in full_text
        assert "greetings" in full_text

    @pytest.mark.asyncio
    async def test_multiple_responses(self, chunker):
        """Handle multiple consecutive LLM responses."""
        # First response
        await chunker.process_frame(
            LLMFullResponseStartFrame(), FrameDirection.DOWNSTREAM
        )
        await chunker.process_frame(
            LLMTextFrame(text="First response here. "), FrameDirection.DOWNSTREAM
        )
        await chunker.process_frame(
            LLMFullResponseEndFrame(), FrameDirection.DOWNSTREAM
        )
        chunker.push_frame.reset_mock()

        # Second response (buffer should be clean)
        await chunker.process_frame(
            LLMFullResponseStartFrame(), FrameDirection.DOWNSTREAM
        )
        await chunker.process_frame(
            LLMTextFrame(text="Second response. "), FrameDirection.DOWNSTREAM
        )

        # Check emitted frames
        calls = chunker.push_frame.call_args_list
        # Should have start frame and text frame
        emitted_texts = [
            c[0][0].text for c in calls if isinstance(c[0][0], TextFrame)
        ]
        assert "Second response." in emitted_texts
        # Should NOT contain first response
        assert "First response here." not in emitted_texts

    @pytest.mark.asyncio
    async def test_latency_under_threshold(self, chunker):
        """Verify latency from first token to first emit is fast."""
        await chunker.process_frame(
            LLMFullResponseStartFrame(), FrameDirection.DOWNSTREAM
        )

        # Send tokens that form a complete sentence
        start = time.perf_counter()
        await chunker.process_frame(
            LLMTextFrame(text="Hello world. "), FrameDirection.DOWNSTREAM
        )
        end = time.perf_counter()

        # Processing should be nearly instant (well under 300ms)
        processing_time_ms = (end - start) * 1000
        assert processing_time_ms < 50  # Should be < 1ms really, 50ms is generous
