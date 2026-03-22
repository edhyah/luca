"""Pipecat pipeline entry point for the Luca voice AI tutor."""

import asyncio
from typing import Any

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.frames.frames import EndFrame
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.services.elevenlabs.tts import ElevenLabsTTSService
from pipecat.transports.daily.transport import DailyParams, DailyTransport

from luca.curriculum.loader import CurriculumLoader
from luca.pipeline.orchestrator import SessionOrchestrator
from luca.pipeline.streaming_tts import StreamingTTSChunker
from luca.pipeline.tts_relay import TTSFrameRelay
from luca.utils.config import get_settings
from luca.utils.logging import get_logger

logger = get_logger("bot")


async def create_bot(room_url: str, token: str, student_id: str = "test-student") -> None:
    """Create and run the Pipecat bot pipeline.

    Args:
        room_url: Daily room URL.
        token: Daily meeting token.
        student_id: Student identifier for session tracking.
    """
    settings = get_settings()

    # Load curriculum
    loader = CurriculumLoader()
    curriculum = loader.load_curriculum("data/curriculum.json")

    # Create VAD analyzer
    vad = SileroVADAnalyzer(sample_rate=16000)

    # Create STT service (Deepgram)
    stt = DeepgramSTTService(
        api_key=settings.deepgram_api_key,
        model="nova-2",
    )

    # Create TTS service (ElevenLabs)
    # Note: Using settings pattern to avoid deprecation warning
    tts = ElevenLabsTTSService(
        api_key=settings.elevenlabs_api_key,
        voice_id=settings.tts_voice_id,
    )

    # Create pipeline components
    orchestrator = SessionOrchestrator(curriculum, student_id)
    tts_chunker = StreamingTTSChunker()
    tts_relay = TTSFrameRelay()

    # Initialize session (loads student data, plans session)
    await orchestrator.initialize_session()

    # Create transport with VAD
    transport = DailyTransport(
        room_url,
        token,
        "Luca",
        DailyParams(
            audio_out_enabled=True,
            audio_in_enabled=True,
            vad_enabled=True,
            vad_analyzer=vad,
            transcription_enabled=False,  # We use Deepgram STT separately
        ),
    )

    # Wire the full pipeline
    # Note: tts_relay sits after TTS to relay TTSStarted/StoppedFrame upstream
    # to the orchestrator, which needs them for state transitions
    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            orchestrator,
            tts_chunker,
            tts,
            tts_relay,
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
        await orchestrator.cleanup()
        await task.queue_frame(EndFrame())

    runner = PipelineRunner()
    await runner.run(task)


async def main() -> None:
    """Main entry point for testing the bot directly."""
    logger.info("Bot module loaded - use bot_runner.py to start the server")


if __name__ == "__main__":
    asyncio.run(main())
