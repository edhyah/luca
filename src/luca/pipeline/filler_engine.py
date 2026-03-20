"""Filler audio and THINKING_PAUSE frame processor."""

import asyncio
import random
from enum import Enum
from pathlib import Path

from pipecat.frames.frames import (
    Frame,
    OutputAudioRawFrame,
    TextFrame,
    UserStoppedSpeakingFrame,
    VADUserStartedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from luca.pipeline.frames import HintDeliveredFrame, TurnContextFrame
from luca.pipeline.pattern_matcher import MatchSignal
from luca.utils.logging import get_logger

logger = get_logger("pipeline.filler_engine")


class FillerState(Enum):
    """States of the filler engine state machine."""

    NORMAL = "normal"
    THINKING_PAUSE = "thinking_pause"
    HINTING = "hinting"


class FillerEngine(FrameProcessor):
    """Handles filler audio playback during thinking pauses.

    State machine with three states:
    - NORMAL: Play filler immediately on end-of-speech
    - THINKING_PAUSE: Suppress filler, wait for speech or timeout
    - HINTING: Delivering graduated hint via TTS

    Features:
    - Immediate filler playback (<50ms) to mask latency
    - Pool selection based on pattern matcher signals
    - Graduated hints for construction challenges
    - Double-filler support for slow LLM responses
    """

    # Silence windows by difficulty (min_seconds, max_seconds)
    SILENCE_WINDOWS: dict[int, tuple[float, float]] = {
        1: (3.0, 5.0),
        2: (5.0, 7.0),
        3: (8.0, 12.0),
    }
    POST_HINT_WINDOW: tuple[float, float] = (3.0, 5.0)
    DOUBLE_FILLER_DELAY: float = 1.5

    def __init__(
        self,
        filler_dir: Path | str = Path("assets/fillers"),
        sample_rate: int = 24000,
        num_channels: int = 1,
        double_filler_enabled: bool = True,
    ) -> None:
        """Initialize the FillerEngine.

        Args:
            filler_dir: Directory containing filler audio files.
            sample_rate: Audio sample rate for playback.
            num_channels: Number of audio channels.
            double_filler_enabled: Whether to enable double-filler for slow paths.
        """
        super().__init__()

        self._filler_dir = Path(filler_dir)
        self._sample_rate = sample_rate
        self._num_channels = num_channels
        self._double_filler_enabled = double_filler_enabled

        # Audio pools: pool_name -> list of PCM audio bytes
        self._audio_pools: dict[str, list[bytes]] = {
            "affirmative": [],
            "thoughtful": [],
            "neutral": [],
        }

        # State machine
        self._state = FillerState.NORMAL
        self._current_difficulty = 1
        self._hints: list[str] = []
        self._hints_given = 0
        self._current_signal: MatchSignal | None = None

        # Timers
        self._silence_timer: asyncio.Task[None] | None = None
        self._double_filler_timer: asyncio.Task[None] | None = None

        # Load audio files
        self._load_audio_pools()

    def _load_audio_pools(self) -> None:
        """Load filler audio files from disk and convert to PCM."""
        try:
            from pydub import AudioSegment
        except ImportError:
            logger.warning("pydub not installed, filler audio disabled")
            return

        for pool_name in self._audio_pools:
            pool_dir = self._filler_dir / pool_name
            if not pool_dir.exists():
                logger.warning(f"Filler directory not found: {pool_dir}")
                continue

            for audio_file in pool_dir.glob("*.mp3"):
                try:
                    pcm_data = self._convert_to_pcm(audio_file)
                    self._audio_pools[pool_name].append(pcm_data)
                    logger.debug(f"Loaded filler: {audio_file.name}")
                except Exception as e:
                    logger.error(f"Failed to load filler {audio_file}: {e}")

            logger.info(
                f"Loaded {len(self._audio_pools[pool_name])} fillers for pool '{pool_name}'"
            )

    def _convert_to_pcm(self, audio_file: Path) -> bytes:
        """Convert MP3 file to raw PCM audio data.

        Args:
            audio_file: Path to the MP3 file.

        Returns:
            Raw PCM audio bytes at configured sample rate and channels.
        """
        from pydub import AudioSegment

        audio = AudioSegment.from_mp3(audio_file)
        audio = audio.set_frame_rate(self._sample_rate).set_channels(self._num_channels)
        # Convert to 16-bit signed little-endian PCM
        audio = audio.set_sample_width(2)
        return bytes(audio.raw_data)

    def _select_pool(self) -> str:
        """Select the appropriate filler pool based on evaluation signal.

        Returns:
            Pool name: 'affirmative', 'thoughtful', or 'neutral'.
        """
        if self._current_signal == MatchSignal.CLEAR_MATCH:
            return "affirmative"
        elif self._current_signal in (MatchSignal.CLEAR_MISS, MatchSignal.AMBIGUOUS):
            return "thoughtful"
        else:
            return "neutral"

    def _get_random_filler(self, pool_name: str) -> bytes | None:
        """Get a random filler from the specified pool.

        Args:
            pool_name: Name of the pool to select from.

        Returns:
            PCM audio bytes or None if pool is empty.
        """
        pool = self._audio_pools.get(pool_name, [])
        if not pool:
            return None
        return random.choice(pool)

    async def _play_filler(self, pool_name: str | None = None) -> None:
        """Play a filler audio clip.

        Args:
            pool_name: Pool to select from, or None to auto-select.
        """
        if pool_name is None:
            pool_name = self._select_pool()

        filler_audio = self._get_random_filler(pool_name)
        if filler_audio is None:
            logger.debug(f"No fillers available in pool '{pool_name}'")
            return

        # Create and push audio frame
        audio_frame = OutputAudioRawFrame(
            audio=filler_audio,
            sample_rate=self._sample_rate,
            num_channels=self._num_channels,
        )
        await self.push_frame(audio_frame, FrameDirection.DOWNSTREAM)
        logger.debug(f"Played filler from pool '{pool_name}'")

    async def _schedule_double_filler(self) -> None:
        """Schedule a second filler after a delay (for slow LLM paths)."""
        if not self._double_filler_enabled:
            return

        self._cancel_double_filler_timer()
        self._double_filler_timer = asyncio.create_task(self._double_filler_callback())

    async def _double_filler_callback(self) -> None:
        """Callback that plays the second filler after delay."""
        try:
            await asyncio.sleep(self.DOUBLE_FILLER_DELAY)
            # Always use neutral pool for second filler
            await self._play_filler("neutral")
            logger.debug("Played double-filler")
        except asyncio.CancelledError:
            pass

    def _cancel_double_filler_timer(self) -> None:
        """Cancel any pending double-filler timer."""
        if self._double_filler_timer and not self._double_filler_timer.done():
            self._double_filler_timer.cancel()
            self._double_filler_timer = None

    async def _start_silence_timer(self) -> None:
        """Start the silence timer for THINKING_PAUSE mode."""
        self._cancel_silence_timer()

        # Select window based on difficulty and hints given
        if self._hints_given > 0:
            window = self.POST_HINT_WINDOW
        else:
            window = self.SILENCE_WINDOWS.get(
                self._current_difficulty,
                self.SILENCE_WINDOWS[3],  # Default to longest window
            )

        delay = random.uniform(*window)
        self._silence_timer = asyncio.create_task(self._silence_timeout(delay))
        logger.debug(f"Started silence timer: {delay:.1f}s (hints_given={self._hints_given})")

    async def _silence_timeout(self, delay: float) -> None:
        """Handle silence timeout by delivering a hint.

        Args:
            delay: Seconds to wait before timing out.
        """
        try:
            await asyncio.sleep(delay)
            await self._deliver_hint()
        except asyncio.CancelledError:
            pass

    def _cancel_silence_timer(self) -> None:
        """Cancel any pending silence timer."""
        if self._silence_timer and not self._silence_timer.done():
            self._silence_timer.cancel()
            self._silence_timer = None

    async def _deliver_hint(self) -> None:
        """Deliver the next graduated hint via TTS."""
        if self._hints_given >= len(self._hints):
            logger.debug("No more hints available")
            return

        hint = self._hints[self._hints_given]
        hint_index = self._hints_given
        self._hints_given += 1
        self._state = FillerState.HINTING

        # Push hint text to TTS
        hint_frame = TextFrame(text=hint)
        await self.push_frame(hint_frame, FrameDirection.DOWNSTREAM)
        logger.info(f"Delivered hint {self._hints_given}/{len(self._hints)}: {hint[:50]}...")

        # Notify orchestrator that a hint was delivered
        hint_delivered_frame = HintDeliveredFrame(
            hint_index=hint_index,
            total_hints=len(self._hints),
        )
        await self.push_frame(hint_delivered_frame, FrameDirection.UPSTREAM)

        # Restart timer with shorter post-hint window
        self._state = FillerState.THINKING_PAUSE
        await self._start_silence_timer()

    def get_hints_given(self) -> int:
        """Return the number of hints given in the current turn.

        This is used by the context builder to track hint usage.
        """
        return self._hints_given

    def reset_hint_counter(self) -> None:
        """Reset the hint counter for a new turn."""
        self._hints_given = 0

    def _enter_thinking_pause(self) -> None:
        """Enter THINKING_PAUSE mode."""
        self._state = FillerState.THINKING_PAUSE
        logger.debug(
            f"Entering THINKING_PAUSE (difficulty={self._current_difficulty}, "
            f"hints={len(self._hints)})"
        )

    def _enter_normal(self) -> None:
        """Enter NORMAL mode."""
        self._state = FillerState.NORMAL
        self._cancel_silence_timer()
        logger.debug("Entering NORMAL mode")

    async def _handle_turn_context(self, frame: TurnContextFrame) -> None:
        """Handle TurnContextFrame from orchestrator.

        Args:
            frame: Turn context with difficulty, hints, and signal.
        """
        self._current_difficulty = frame.difficulty
        self._hints = frame.hints
        self._current_signal = frame.evaluation_signal
        self.reset_hint_counter()

        # Enter THINKING_PAUSE for difficulty >= 2
        if frame.difficulty >= 2:
            self._enter_thinking_pause()
        else:
            self._enter_normal()

    async def _handle_user_stopped_speaking(self) -> None:
        """Handle end-of-speech event."""
        if self._state == FillerState.NORMAL:
            # Play filler immediately
            await self._play_filler()
            # Schedule double-filler for slow path
            await self._schedule_double_filler()
        elif self._state == FillerState.THINKING_PAUSE:
            # Start silence timer instead of playing filler
            await self._start_silence_timer()

    async def _handle_user_started_speaking(self) -> None:
        """Handle VAD detected speech start (partial speech)."""
        # Cancel silence timer - user is trying to speak
        self._cancel_silence_timer()
        self._cancel_double_filler_timer()
        logger.debug("VAD speech detected, canceling timers")

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        """Process frames and inject filler audio when appropriate.

        Args:
            frame: The frame to process.
            direction: Frame direction (upstream/downstream).
        """
        # Handle custom frames
        if isinstance(frame, TurnContextFrame):
            await self._handle_turn_context(frame)
            # Don't pass TurnContextFrame downstream - it's internal
            return

        # Handle VAD frames
        if isinstance(frame, UserStoppedSpeakingFrame):
            await self._handle_user_stopped_speaking()
        elif isinstance(frame, VADUserStartedSpeakingFrame):
            await self._handle_user_started_speaking()

        # Pass all other frames through
        await self.push_frame(frame, direction)
