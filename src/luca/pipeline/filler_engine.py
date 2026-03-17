"""Filler audio and THINKING_PAUSE frame processor."""

from pipecat.frames.frames import Frame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from luca.utils.logging import get_logger

logger = get_logger("pipeline.filler_engine")


class FillerEngine(FrameProcessor):
    """Handles filler audio playback during thinking pauses."""

    def __init__(self) -> None:
        super().__init__()
        # TODO: Load filler audio files from assets/fillers/

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        """Process frames and inject filler audio when appropriate."""
        # TODO: Implement filler logic
        await self.push_frame(frame, direction)
