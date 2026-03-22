"""Relay TTS state frames upstream to the orchestrator."""

from pipecat.frames.frames import Frame, StartFrame, TTSStartedFrame, TTSStoppedFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor


class TTSFrameRelay(FrameProcessor):
    """Relays TTS state frames both downstream and upstream.

    Pipecat's TTS services emit TTSStartedFrame and TTSStoppedFrame downstream.
    The SessionOrchestrator needs to receive these frames to manage state
    transitions, but it's positioned upstream of the TTS service.

    This processor sits after TTS and relays state frames upstream while
    also passing them downstream as normal.
    """

    def __init__(self) -> None:
        super().__init__()
        self._pipeline_started = False

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        # Handle StartFrame to set pipecat's internal _started flag
        if isinstance(frame, StartFrame):
            await super().process_frame(frame, direction)
            self._pipeline_started = True
            await self.push_frame(frame, direction)
            return

        # Silently drop frames before pipeline is started (avoids pipecat warnings)
        if not self._pipeline_started:
            return

        # Always pass frames through in their original direction
        await self.push_frame(frame, direction)

        # Only relay TTS state frames that are flowing downstream (from TTS)
        # Don't relay frames already going upstream to avoid loops
        if direction == FrameDirection.DOWNSTREAM:
            if isinstance(frame, (TTSStartedFrame, TTSStoppedFrame)):
                await self.push_frame(frame, FrameDirection.UPSTREAM)
