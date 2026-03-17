"""Pipecat pipeline entry point for the Luca voice AI tutor."""

import asyncio
from typing import Any

from pipecat.frames.frames import EndFrame, Frame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.transports.daily.transport import DailyParams, DailyTransport

from luca.utils.config import get_settings
from luca.utils.logging import get_logger

logger = get_logger("bot")


class EchoProcessor(FrameProcessor):
    """Placeholder processor that logs frames (for initial scaffolding)."""

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        """Process incoming frames."""
        await self.push_frame(frame, direction)


async def create_bot(room_url: str, token: str) -> None:
    """Create and run the Pipecat bot pipeline."""
    settings = get_settings()

    transport = DailyTransport(
        room_url,
        token,
        "Luca",
        DailyParams(
            audio_out_enabled=True,
            audio_in_enabled=True,
            vad_enabled=True,
            vad_analyzer=None,  # Will be configured with Silero
            transcription_enabled=False,  # We'll use Deepgram separately
        ),
    )

    # Placeholder pipeline - will be expanded with full processors
    pipeline = Pipeline(
        [
            transport.input(),
            EchoProcessor(),
            transport.output(),
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            allow_interruptions=True,
            enable_metrics=True,
        ),
    )

    @transport.event_handler("on_participant_joined")
    async def on_participant_joined(transport: Any, participant: Any) -> None:
        logger.info(f"Participant joined: {participant.get('id', 'unknown')}")

    @transport.event_handler("on_participant_left")
    async def on_participant_left(transport: Any, participant: Any, reason: Any) -> None:
        logger.info(f"Participant left: {participant.get('id', 'unknown')}")
        await task.queue_frame(EndFrame())

    runner = PipelineRunner()
    await runner.run(task)


async def main() -> None:
    """Main entry point for testing the bot directly."""
    logger.info("Bot module loaded - use bot_runner.py to start the server")


if __name__ == "__main__":
    asyncio.run(main())
