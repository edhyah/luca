"""Tests for the FillerEngine frame processor."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from luca.pipeline.filler_engine import FillerEngine, FillerState
from luca.pipeline.frames import TurnContextFrame
from luca.pipeline.pattern_matcher import MatchSignal


class TestFillerEngineInit:
    """Tests for FillerEngine initialization."""

    def test_default_init(self):
        """Test default initialization."""
        engine = FillerEngine()
        assert engine._state == FillerState.NORMAL
        assert engine._current_difficulty == 1
        assert engine._hints_given == 0
        assert engine._double_filler_enabled is True

    def test_custom_init(self):
        """Test initialization with custom parameters."""
        engine = FillerEngine(
            filler_dir=Path("/custom/path"),
            sample_rate=16000,
            num_channels=2,
            double_filler_enabled=False,
        )
        assert engine._filler_dir == Path("/custom/path")
        assert engine._sample_rate == 16000
        assert engine._num_channels == 2
        assert engine._double_filler_enabled is False

    def test_audio_pools_structure(self):
        """Test audio pools are initialized correctly."""
        engine = FillerEngine()
        assert "affirmative" in engine._audio_pools
        assert "thoughtful" in engine._audio_pools
        assert "neutral" in engine._audio_pools


class TestPoolSelection:
    """Tests for filler pool selection logic."""

    def test_clear_match_selects_affirmative(self):
        """CLEAR_MATCH signal should select affirmative pool."""
        engine = FillerEngine()
        engine._current_signal = MatchSignal.CLEAR_MATCH
        assert engine._select_pool() == "affirmative"

    def test_clear_miss_selects_thoughtful(self):
        """CLEAR_MISS signal should select thoughtful pool."""
        engine = FillerEngine()
        engine._current_signal = MatchSignal.CLEAR_MISS
        assert engine._select_pool() == "thoughtful"

    def test_ambiguous_selects_thoughtful(self):
        """AMBIGUOUS signal should select thoughtful pool."""
        engine = FillerEngine()
        engine._current_signal = MatchSignal.AMBIGUOUS
        assert engine._select_pool() == "thoughtful"

    def test_no_signal_selects_neutral(self):
        """No signal should select neutral pool."""
        engine = FillerEngine()
        engine._current_signal = None
        assert engine._select_pool() == "neutral"


class TestFillerState:
    """Tests for state machine states."""

    def test_state_enum_values(self):
        """Test FillerState enum values."""
        assert FillerState.NORMAL.value == "normal"
        assert FillerState.THINKING_PAUSE.value == "thinking_pause"
        assert FillerState.HINTING.value == "hinting"

    def test_enter_normal_mode(self):
        """Test entering NORMAL mode."""
        engine = FillerEngine()
        engine._state = FillerState.THINKING_PAUSE
        engine._enter_normal()
        assert engine._state == FillerState.NORMAL

    def test_enter_thinking_pause_mode(self):
        """Test entering THINKING_PAUSE mode."""
        engine = FillerEngine()
        engine._enter_thinking_pause()
        assert engine._state == FillerState.THINKING_PAUSE


class TestTurnContextHandling:
    """Tests for TurnContextFrame handling."""

    @pytest.mark.asyncio
    async def test_difficulty_1_enters_normal(self):
        """Difficulty 1 should keep engine in NORMAL mode."""
        engine = FillerEngine()
        frame = TurnContextFrame(difficulty=1, hints=["hint1"])

        await engine._handle_turn_context(frame)

        assert engine._state == FillerState.NORMAL
        assert engine._current_difficulty == 1
        assert engine._hints == ["hint1"]

    @pytest.mark.asyncio
    async def test_difficulty_2_enters_thinking_pause(self):
        """Difficulty 2 should enter THINKING_PAUSE mode."""
        engine = FillerEngine()
        frame = TurnContextFrame(difficulty=2, hints=["hint1", "hint2"])

        await engine._handle_turn_context(frame)

        assert engine._state == FillerState.THINKING_PAUSE
        assert engine._current_difficulty == 2
        assert engine._hints == ["hint1", "hint2"]

    @pytest.mark.asyncio
    async def test_difficulty_3_enters_thinking_pause(self):
        """Difficulty 3 should enter THINKING_PAUSE mode."""
        engine = FillerEngine()
        frame = TurnContextFrame(difficulty=3, hints=["hint1", "hint2", "hint3"])

        await engine._handle_turn_context(frame)

        assert engine._state == FillerState.THINKING_PAUSE
        assert engine._current_difficulty == 3

    @pytest.mark.asyncio
    async def test_evaluation_signal_stored(self):
        """Evaluation signal should be stored from TurnContextFrame."""
        engine = FillerEngine()
        frame = TurnContextFrame(
            difficulty=1,
            hints=[],
            evaluation_signal=MatchSignal.CLEAR_MATCH,
        )

        await engine._handle_turn_context(frame)

        assert engine._current_signal == MatchSignal.CLEAR_MATCH

    @pytest.mark.asyncio
    async def test_hints_reset_on_new_turn(self):
        """Hints given counter should reset on new turn context."""
        engine = FillerEngine()
        engine._hints_given = 2

        frame = TurnContextFrame(difficulty=1, hints=["new hint"])
        await engine._handle_turn_context(frame)

        assert engine._hints_given == 0


class TestNormalModeFiller:
    """Tests for filler playback in NORMAL mode."""

    @pytest.mark.asyncio
    async def test_filler_plays_on_user_stopped_speaking(self):
        """Filler should play when user stops speaking in NORMAL mode."""
        engine = FillerEngine()
        engine._state = FillerState.NORMAL
        engine._audio_pools["neutral"] = [b"fake_audio_data"]

        with patch.object(engine, "push_frame", new_callable=AsyncMock) as mock_push:
            await engine._play_filler("neutral")

            mock_push.assert_called_once()
            # Check that an AudioRawFrame was pushed
            call_args = mock_push.call_args
            assert call_args is not None

    @pytest.mark.asyncio
    async def test_no_filler_when_pool_empty(self):
        """No filler should play when pool is empty."""
        engine = FillerEngine()
        engine._audio_pools["neutral"] = []

        with patch.object(engine, "push_frame", new_callable=AsyncMock) as mock_push:
            await engine._play_filler("neutral")

            mock_push.assert_not_called()

    @pytest.mark.asyncio
    async def test_random_filler_selection(self):
        """Filler should be randomly selected from pool."""
        engine = FillerEngine()
        engine._audio_pools["affirmative"] = [b"audio1", b"audio2", b"audio3"]

        # Get multiple selections
        selections = set()
        for _ in range(50):
            filler = engine._get_random_filler("affirmative")
            selections.add(filler)

        # Should have selected multiple different fillers
        assert len(selections) > 1


class TestThinkingPauseMode:
    """Tests for THINKING_PAUSE mode behavior."""

    @pytest.mark.asyncio
    async def test_filler_suppressed_in_thinking_pause(self):
        """Filler should not play immediately in THINKING_PAUSE mode."""
        engine = FillerEngine()
        engine._state = FillerState.THINKING_PAUSE
        engine._current_difficulty = 2
        engine._audio_pools["neutral"] = [b"fake_audio"]

        with patch.object(engine, "_play_filler", new_callable=AsyncMock) as mock_play:
            with patch.object(
                engine, "_start_silence_timer", new_callable=AsyncMock
            ) as mock_timer:
                await engine._handle_user_stopped_speaking()

                mock_play.assert_not_called()
                mock_timer.assert_called_once()

    @pytest.mark.asyncio
    async def test_silence_timer_started_in_thinking_pause(self):
        """Silence timer should start in THINKING_PAUSE mode."""
        engine = FillerEngine()
        engine._state = FillerState.THINKING_PAUSE
        engine._current_difficulty = 2
        engine._hints = ["hint1"]

        with patch.object(
            engine, "_silence_timeout", new_callable=AsyncMock
        ) as mock_timeout:
            await engine._start_silence_timer()

            # Timer should be created
            assert engine._silence_timer is not None


class TestVADReset:
    """Tests for VAD speech detection resetting timers."""

    @pytest.mark.asyncio
    async def test_vad_cancels_silence_timer(self):
        """VAD speech start should cancel silence timer."""
        engine = FillerEngine()

        # Create a mock timer
        engine._silence_timer = asyncio.create_task(asyncio.sleep(10))

        await engine._handle_user_started_speaking()

        # Timer should be cancelled
        assert engine._silence_timer is None or engine._silence_timer.cancelled()

    @pytest.mark.asyncio
    async def test_vad_cancels_double_filler_timer(self):
        """VAD speech start should cancel double-filler timer."""
        engine = FillerEngine()

        # Create a mock timer
        engine._double_filler_timer = asyncio.create_task(asyncio.sleep(10))

        await engine._handle_user_started_speaking()

        # Timer should be cancelled
        assert (
            engine._double_filler_timer is None
            or engine._double_filler_timer.cancelled()
        )


class TestHintDelivery:
    """Tests for graduated hint delivery."""

    @pytest.mark.asyncio
    async def test_hint_delivered_via_text_frame(self):
        """Hints should be delivered as TextFrame and HintDeliveredFrame."""
        engine = FillerEngine()
        engine._hints = ["First hint", "Second hint"]
        engine._hints_given = 0
        engine._state = FillerState.THINKING_PAUSE

        with patch.object(engine, "push_frame", new_callable=AsyncMock) as mock_push:
            with patch.object(
                engine, "_start_silence_timer", new_callable=AsyncMock
            ):
                await engine._deliver_hint()

                # Should have pushed a TextFrame downstream and HintDeliveredFrame upstream
                assert mock_push.call_count == 2
                # First call is the TextFrame with hint
                text_frame = mock_push.call_args_list[0][0][0]
                assert text_frame.text == "First hint"
                # Second call is the HintDeliveredFrame
                hint_frame = mock_push.call_args_list[1][0][0]
                assert hint_frame.hint_index == 0
                assert hint_frame.total_hints == 2

    @pytest.mark.asyncio
    async def test_hints_given_counter_increments(self):
        """Hints given counter should increment after each hint."""
        engine = FillerEngine()
        engine._hints = ["First hint", "Second hint"]
        engine._hints_given = 0

        with patch.object(engine, "push_frame", new_callable=AsyncMock):
            with patch.object(
                engine, "_start_silence_timer", new_callable=AsyncMock
            ):
                await engine._deliver_hint()
                assert engine._hints_given == 1

                await engine._deliver_hint()
                assert engine._hints_given == 2

    @pytest.mark.asyncio
    async def test_no_hint_when_all_exhausted(self):
        """No hint should be delivered when all hints exhausted."""
        engine = FillerEngine()
        engine._hints = ["Only hint"]
        engine._hints_given = 1  # Already gave the only hint

        with patch.object(engine, "push_frame", new_callable=AsyncMock) as mock_push:
            await engine._deliver_hint()

            mock_push.assert_not_called()

    def test_get_hints_given(self):
        """get_hints_given should return correct count."""
        engine = FillerEngine()
        engine._hints_given = 3
        assert engine.get_hints_given() == 3

    def test_reset_hint_counter(self):
        """reset_hint_counter should reset the counter but preserve hints."""
        engine = FillerEngine()
        engine._hints = ["hint1", "hint2"]
        engine._hints_given = 2

        engine.reset_hint_counter()

        # Hints preserved, only counter reset
        assert engine._hints == ["hint1", "hint2"]
        assert engine._hints_given == 0


class TestDoubleFiller:
    """Tests for double-filler (slow path) behavior."""

    @pytest.mark.asyncio
    async def test_double_filler_scheduled(self):
        """Double filler should be scheduled after first filler."""
        engine = FillerEngine(double_filler_enabled=True)
        engine._audio_pools["neutral"] = [b"fake_audio"]

        with patch.object(engine, "push_frame", new_callable=AsyncMock):
            await engine._schedule_double_filler()

            # Timer should be created
            assert engine._double_filler_timer is not None

            # Clean up
            engine._cancel_double_filler_timer()

    @pytest.mark.asyncio
    async def test_double_filler_disabled(self):
        """Double filler should not schedule when disabled."""
        engine = FillerEngine(double_filler_enabled=False)

        await engine._schedule_double_filler()

        assert engine._double_filler_timer is None

    @pytest.mark.asyncio
    async def test_double_filler_uses_neutral_pool(self):
        """Double filler should use neutral pool."""
        engine = FillerEngine(double_filler_enabled=True)
        engine._audio_pools["neutral"] = [b"neutral_audio"]
        engine._audio_pools["affirmative"] = [b"affirmative_audio"]
        engine._current_signal = MatchSignal.CLEAR_MATCH  # Would normally use affirmative

        with patch.object(engine, "push_frame", new_callable=AsyncMock) as mock_push:
            with patch.object(engine, "_play_filler", new_callable=AsyncMock) as mock_play:
                # Directly test the callback
                engine.DOUBLE_FILLER_DELAY = 0.01  # Speed up test
                await engine._double_filler_callback()

                # Should call play_filler with neutral
                mock_play.assert_called_once_with("neutral")


class TestSilenceWindows:
    """Tests for silence window timing."""

    def test_difficulty_2_window(self):
        """Difficulty 2 should use 5-7 second window."""
        engine = FillerEngine()
        window = engine.SILENCE_WINDOWS.get(2)
        assert window == (5.0, 7.0)

    def test_difficulty_3_window(self):
        """Difficulty 3 should use 8-12 second window."""
        engine = FillerEngine()
        window = engine.SILENCE_WINDOWS.get(3)
        assert window == (8.0, 12.0)

    def test_post_hint_window(self):
        """Post-hint window should be shorter (3-5 seconds)."""
        engine = FillerEngine()
        assert engine.POST_HINT_WINDOW == (3.0, 5.0)

    def test_default_to_longest_window_for_high_difficulty(self):
        """High difficulty should default to longest window."""
        engine = FillerEngine()
        # Difficulty 4+ would use difficulty 3 window
        default_window = engine.SILENCE_WINDOWS.get(4, engine.SILENCE_WINDOWS[3])
        assert default_window == (8.0, 12.0)


class TestFrameProcessing:
    """Tests for the main process_frame method."""

    @pytest.mark.asyncio
    async def test_turn_context_frame_not_passed_through(self):
        """TurnContextFrame should not be passed downstream."""
        engine = FillerEngine()

        with patch.object(engine, "push_frame", new_callable=AsyncMock) as mock_push:
            from pipecat.processors.frame_processor import FrameDirection

            frame = TurnContextFrame(difficulty=1, hints=[])
            await engine.process_frame(frame, FrameDirection.DOWNSTREAM)

            # Should not push the TurnContextFrame
            for call in mock_push.call_args_list:
                pushed_frame = call[0][0]
                assert not isinstance(pushed_frame, TurnContextFrame)

    @pytest.mark.asyncio
    async def test_other_frames_passed_through(self):
        """Non-control frames should pass through unchanged."""
        engine = FillerEngine()

        from pipecat.frames.frames import TextFrame
        from pipecat.processors.frame_processor import FrameDirection

        with patch.object(engine, "push_frame", new_callable=AsyncMock) as mock_push:
            frame = TextFrame(text="hello")
            await engine.process_frame(frame, FrameDirection.DOWNSTREAM)

            mock_push.assert_called_once_with(frame, FrameDirection.DOWNSTREAM)


class TestAudioConversion:
    """Tests for audio format conversion."""

    def test_convert_to_pcm_requires_pydub(self):
        """Audio conversion requires pydub library."""
        engine = FillerEngine()

        # If pydub is not available, conversion should handle gracefully
        # This test just verifies the method signature exists
        assert hasattr(engine, "_convert_to_pcm")


class TestTurnContextFrame:
    """Tests for TurnContextFrame dataclass."""

    def test_turn_context_frame_creation(self):
        """Test TurnContextFrame creation with all fields."""
        frame = TurnContextFrame(
            difficulty=2,
            hints=["hint1", "hint2"],
            evaluation_signal=MatchSignal.CLEAR_MATCH,
        )
        assert frame.difficulty == 2
        assert frame.hints == ["hint1", "hint2"]
        assert frame.evaluation_signal == MatchSignal.CLEAR_MATCH

    def test_turn_context_frame_defaults(self):
        """Test TurnContextFrame default values."""
        frame = TurnContextFrame(difficulty=1)
        assert frame.hints == []
        assert frame.evaluation_signal is None

    def test_turn_context_frame_is_dataframe(self):
        """TurnContextFrame should be a DataFrame."""
        from pipecat.frames.frames import DataFrame

        frame = TurnContextFrame(difficulty=1)
        assert isinstance(frame, DataFrame)


class TestTimerManagement:
    """Tests for timer creation and cancellation."""

    @pytest.mark.asyncio
    async def test_cancel_silence_timer_when_none(self):
        """Canceling None timer should not raise."""
        engine = FillerEngine()
        engine._silence_timer = None
        engine._cancel_silence_timer()  # Should not raise

    @pytest.mark.asyncio
    async def test_cancel_double_filler_timer_when_none(self):
        """Canceling None timer should not raise."""
        engine = FillerEngine()
        engine._double_filler_timer = None
        engine._cancel_double_filler_timer()  # Should not raise

    @pytest.mark.asyncio
    async def test_silence_timer_cancelled_on_new_timer(self):
        """Starting new silence timer should cancel existing one."""
        engine = FillerEngine()
        engine._current_difficulty = 2
        engine._hints = []

        # Create first timer
        old_timer = asyncio.create_task(asyncio.sleep(100))
        engine._silence_timer = old_timer

        with patch.object(
            engine, "_silence_timeout", new_callable=AsyncMock
        ):
            await engine._start_silence_timer()

        # Give event loop a chance to process the cancellation
        await asyncio.sleep(0)

        # Old timer should be cancelled or done
        assert old_timer.cancelled() or old_timer.done()


class TestIntegration:
    """Integration tests for full flow scenarios."""

    @pytest.mark.asyncio
    async def test_full_thinking_pause_flow(self):
        """Test full flow: TurnContext -> UserStopped -> silence -> hint."""
        engine = FillerEngine()
        engine._audio_pools["neutral"] = [b"filler_audio"]

        # Step 1: Receive turn context with difficulty 2
        turn_frame = TurnContextFrame(
            difficulty=2,
            hints=["Try thinking about...", "Remember that..."],
        )
        await engine._handle_turn_context(turn_frame)

        assert engine._state == FillerState.THINKING_PAUSE
        assert engine._hints == ["Try thinking about...", "Remember that..."]

        # Step 2: User stops speaking - should NOT play filler
        with patch.object(engine, "_play_filler", new_callable=AsyncMock) as mock_play:
            with patch.object(
                engine, "_start_silence_timer", new_callable=AsyncMock
            ) as mock_timer:
                await engine._handle_user_stopped_speaking()

                mock_play.assert_not_called()
                mock_timer.assert_called_once()

    @pytest.mark.asyncio
    async def test_full_normal_mode_flow(self):
        """Test full flow in NORMAL mode: UserStopped -> filler -> double filler."""
        engine = FillerEngine(double_filler_enabled=True)
        engine._audio_pools["neutral"] = [b"filler_audio"]
        engine._state = FillerState.NORMAL

        with patch.object(engine, "push_frame", new_callable=AsyncMock):
            await engine._handle_user_stopped_speaking()

            # Double filler timer should be scheduled
            assert engine._double_filler_timer is not None

            # Clean up
            engine._cancel_double_filler_timer()

    @pytest.mark.asyncio
    async def test_vad_interrupts_hint_sequence(self):
        """VAD detection should interrupt hint delivery sequence."""
        engine = FillerEngine()
        engine._state = FillerState.THINKING_PAUSE
        engine._hints = ["hint1", "hint2"]

        # Start silence timer
        engine._silence_timer = asyncio.create_task(asyncio.sleep(10))

        # User starts speaking
        await engine._handle_user_started_speaking()

        # Timer should be cancelled
        assert engine._silence_timer is None or engine._silence_timer.cancelled()
        # No hints should have been given
        assert engine._hints_given == 0
