"""Sentence-boundary chunking for streaming TTS."""

import re

from pipecat.frames.frames import Frame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from luca.utils.logging import get_logger

logger = get_logger("pipeline.streaming_tts")


class StreamingTTSChunker(FrameProcessor):
    """Chunks text at sentence boundaries for smoother TTS streaming."""

    SENTENCE_END_PATTERN = re.compile(r"[.!?]+\s*")

    def __init__(self) -> None:
        super().__init__()
        self.buffer = ""

    def extract_sentences(self, text: str) -> tuple[list[str], str]:
        """Extract complete sentences from text, returning sentences and remaining buffer."""
        sentences: list[str] = []
        remaining = text

        while True:
            match = self.SENTENCE_END_PATTERN.search(remaining)
            if match:
                sentence = remaining[: match.end()].strip()
                if sentence:
                    sentences.append(sentence)
                remaining = remaining[match.end() :]
            else:
                break

        return sentences, remaining

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        """Process frames and chunk text at sentence boundaries."""
        # TODO: Implement sentence chunking for LLM text output frames
        await self.push_frame(frame, direction)
