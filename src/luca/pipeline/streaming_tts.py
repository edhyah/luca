"""Sentence-boundary chunking for streaming TTS."""

import re
import time

from pipecat.frames.frames import (
    Frame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
    StartFrame,
    TextFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from luca.utils.logging import get_logger

logger = get_logger("pipeline.streaming_tts")


class StreamingTTSChunker(FrameProcessor):
    """Chunks text at sentence boundaries for smoother TTS streaming.

    This processor buffers streaming LLM tokens and emits complete clauses
    at sentence boundaries for natural TTS prosody. It detects:
    - Sentence endings: . ! ?
    - Clause breaks: comma + conjunction (and, but, so, or, yet)

    The processor also tracks timing from first token to first emit for
    latency verification (target: < 300ms).
    """

    # Pattern for sentence endings: period, question mark, exclamation mark
    SENTENCE_END_PATTERN = re.compile(r"[.!?]+\s*")

    # Pattern for clause breaks: comma followed by conjunction
    # Captures the comma separately so we can keep it with the first clause
    CLAUSE_BREAK_PATTERN = re.compile(r"(,)\s+(and|but|so|or|yet)\s", re.IGNORECASE)

    # Minimum characters before emitting a chunk (avoids awkward short TTS outputs)
    MIN_CHUNK_SIZE = 10

    def __init__(self) -> None:
        super().__init__()
        self._buffer = ""
        self._first_token_time: float | None = None
        self._first_emit_time: float | None = None
        self._pipeline_started = False

    def extract_sentences(self, text: str) -> tuple[list[str], str]:
        """Extract complete sentences/clauses from text.

        Returns a tuple of (extracted_sentences, remaining_buffer).

        Splits on:
        - Sentence endings: . ! ?
        - Clause breaks: comma + conjunction (and, but, so, or, yet)

        For clause breaks, the comma stays with the first clause and the
        conjunction starts the second clause.
        """
        sentences: list[str] = []
        remaining = text

        while True:
            # Find the earliest split point (sentence end or clause break)
            sentence_match = self.SENTENCE_END_PATTERN.search(remaining)
            clause_match = self.CLAUSE_BREAK_PATTERN.search(remaining)

            # Determine which comes first
            sentence_pos = sentence_match.start() if sentence_match else float("inf")
            clause_pos = clause_match.start() if clause_match else float("inf")

            if sentence_pos == float("inf") and clause_pos == float("inf"):
                # No split points found
                break

            if sentence_pos <= clause_pos and sentence_match:
                # Sentence ending comes first (or equal)
                sentence = remaining[: sentence_match.end()].strip()
                if sentence and len(sentence) >= self.MIN_CHUNK_SIZE:
                    sentences.append(sentence)
                    remaining = remaining[sentence_match.end() :]
                elif sentence:
                    # Chunk too short, keep in buffer and stop looking
                    break
                else:
                    remaining = remaining[sentence_match.end() :]
            elif clause_match:
                # Clause break comes first
                # Split before the conjunction, keeping comma with first clause
                comma_end = clause_match.start() + 1  # Include the comma
                sentence = remaining[:comma_end].strip()
                if sentence and len(sentence) >= self.MIN_CHUNK_SIZE:
                    sentences.append(sentence)
                    # Start after comma+space, at the conjunction
                    remaining = remaining[clause_match.start() + 2 :].lstrip()
                else:
                    # Chunk too short, keep in buffer and stop looking
                    break

        return sentences, remaining

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        """Process frames and chunk text at sentence boundaries.

        Handles:
        - StartFrame: Initialize pipeline started state
        - LLMFullResponseStartFrame: Reset buffer and timing
        - LLMTextFrame: Buffer text, extract and emit complete sentences
        - LLMFullResponseEndFrame: Flush remaining buffer
        - Other frames: Pass through unchanged
        """
        # Handle StartFrame to set pipecat's internal _started flag
        if isinstance(frame, StartFrame):
            await super().process_frame(frame, direction)
            self._pipeline_started = True
            # Push StartFrame downstream so other processors receive it
            await self.push_frame(frame, direction)
            return

        # Silently drop frames before pipeline is started (avoids pipecat warnings)
        if not self._pipeline_started:
            return

        if isinstance(frame, LLMFullResponseStartFrame):
            # Reset state for new response
            self._buffer = ""
            self._first_token_time = None
            self._first_emit_time = None
            await self.push_frame(frame, direction)

        elif isinstance(frame, LLMTextFrame):
            # Track first token time
            if self._first_token_time is None:
                self._first_token_time = time.perf_counter()

            # Append to buffer and extract sentences
            self._buffer += frame.text
            sentences, self._buffer = self.extract_sentences(self._buffer)

            # Emit each complete sentence as a TextFrame
            for sentence in sentences:
                # Track first emit time and log latency
                if self._first_emit_time is None:
                    self._first_emit_time = time.perf_counter()
                    latency_ms = (self._first_emit_time - self._first_token_time) * 1000
                    logger.debug(
                        "First chunk latency: %.2fms (target: <300ms)", latency_ms
                    )

                await self.push_frame(TextFrame(text=sentence), direction)

        elif isinstance(frame, LLMFullResponseEndFrame):
            # Flush remaining buffer
            if self._buffer.strip():
                if self._first_emit_time is None and self._first_token_time is not None:
                    self._first_emit_time = time.perf_counter()
                    latency_ms = (self._first_emit_time - self._first_token_time) * 1000
                    logger.debug(
                        "First chunk latency (on flush): %.2fms (target: <300ms)",
                        latency_ms,
                    )

                await self.push_frame(TextFrame(text=self._buffer.strip()), direction)
            self._buffer = ""
            await self.push_frame(frame, direction)

        else:
            # Pass through all other frames unchanged
            await self.push_frame(frame, direction)
