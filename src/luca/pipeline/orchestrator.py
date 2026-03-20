"""Central state machine orchestrating the tutoring session.

The SessionOrchestrator is the main Pipecat FrameProcessor that wires
all Phase 1 components together into a working voice tutoring session.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from pipecat.frames.frames import (
    Frame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
    TextFrame,
    TranscriptionFrame,
    TTSStartedFrame,
    TTSStoppedFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from luca.curriculum.engine import CurriculumEngine
from luca.pipeline.frames import HintDeliveredFrame, TurnContextFrame
from luca.pipeline.off_script import OffScriptDetector, OffScriptType
from luca.pipeline.pattern_matcher import MatchResult, MatchSignal, PatternMatcher
from luca.student.model import StudentModel
from luca.student.session_state import SessionState
from luca.student.triggers import TriggerEvent, TriggerType
from luca.tutor.agent import TutorAgent
from luca.tutor.context_builder import ContextBuilder
from luca.tutor.context_format import TurnContext
from luca.utils.logging import get_logger

if TYPE_CHECKING:
    from luca.curriculum.models import Curriculum

logger = get_logger("pipeline.orchestrator")


class OrchestratorState(Enum):
    """States of the tutoring session state machine."""

    INITIALIZING = "initializing"  # Session starting up
    WAITING_FOR_SPEECH = "waiting"  # Waiting for student input (difficulty 1)
    THINKING_PAUSE = "thinking_pause"  # Thinking pause active (difficulty >= 2)
    EVALUATING = "evaluating"  # Processing student response
    GENERATING = "generating"  # LLM generating response
    SPEAKING = "speaking"  # TTS playing tutor response


@dataclass
class PrecomputedBranch:
    """Pre-computed context for fast-path response."""

    context: TurnContext
    system_prompt: str


@dataclass
class PrecomputedBranches:
    """Pre-computed branches for CLEAR_MATCH and CLEAR_MISS outcomes."""

    correct: PrecomputedBranch | None = None
    incorrect: PrecomputedBranch | None = None
    timestamp: float = field(default_factory=time.perf_counter)


class SessionOrchestrator(FrameProcessor):
    """Central state machine for managing the tutoring session flow.

    Responsibilities:
    - State machine transitions between session phases
    - Pre-computation of correct/incorrect context branches during think time
    - Routing based on MatchSignal (CLEAR_MATCH/CLEAR_MISS/AMBIGUOUS)
    - Push TurnContextFrame to configure filler engine
    - Track hints given via HintDeliveredFrame callback
    - Record responses to student model (triggers BKT + teaching briefs)
    - Advance scaffold steps and concepts via curriculum engine
    - Detect and handle off-script requests (repeat, help, skip, etc.)
    """

    def __init__(
        self,
        curriculum: Curriculum,
        student_id: str,
        student_model: StudentModel | None = None,
        curriculum_engine: CurriculumEngine | None = None,
        tutor_agent: TutorAgent | None = None,
        context_builder: ContextBuilder | None = None,
        pattern_matcher: PatternMatcher | None = None,
        session_state: SessionState | None = None,
    ) -> None:
        """Initialize the orchestrator.

        Args:
            curriculum: The loaded curriculum.
            student_id: Unique student identifier.
            student_model: Student model for BKT and briefs (created if None).
            curriculum_engine: Curriculum engine for progression (created if None).
            tutor_agent: Tutor agent for LLM responses (created if None).
            context_builder: Context builder for prompts (created if None).
            pattern_matcher: Pattern matcher for evaluation (created if None).
            session_state: Session state tracker (created if None).
        """
        super().__init__()

        # Core state
        self.state = OrchestratorState.INITIALIZING
        self.curriculum = curriculum
        self.student_id = student_id

        # Initialize components
        self._student_model = student_model or StudentModel(student_id, curriculum)
        self._curriculum_engine = curriculum_engine or CurriculumEngine()
        self._tutor_agent = tutor_agent or TutorAgent()
        self._context_builder = context_builder or ContextBuilder()
        self._pattern_matcher = pattern_matcher or PatternMatcher()
        self._session_state = session_state or SessionState(student_id, curriculum)
        self._off_script_detector = OffScriptDetector()

        # Pre-computed branches for fast path
        self._precomputed: PrecomputedBranches | None = None

        # Turn tracking
        self._hints_given_this_turn = 0
        self._turn_start_time: float | None = None
        self._last_was_review = False

        # Session plan
        self._session_plan: list[tuple[str, bool]] = []
        self._session_plan_index = 0

        # Pending teaching brief tasks
        self._pending_brief_tasks: list[asyncio.Task[None]] = []

        # Load curriculum into engine
        if curriculum_engine is None:
            self._curriculum_engine.curriculum = curriculum
            self._curriculum_engine.dag = curriculum.build_dag()

    async def initialize_session(self) -> None:
        """Initialize the session with curriculum and student data.

        Should be called before processing begins to:
        - Load student model from persistence
        - Plan the session
        - Set up the first concept
        """
        logger.info(f"Initializing session for student {self.student_id}")

        # Load student data
        await self._student_model.load()

        # Plan the session
        mastery = self._student_model.get_all_mastery()
        self._session_plan = self._curriculum_engine.plan_session(mastery)

        if not self._session_plan:
            logger.warning("No concepts available for session")
            return

        logger.info(f"Session plan: {len(self._session_plan)} concepts")

        # Start with first concept
        first_concept_id, is_review = self._session_plan[0]
        self._session_plan_index = 0
        self._last_was_review = is_review

        await self._advance_to_concept(first_concept_id)

    async def _advance_to_concept(self, concept_id: str) -> None:
        """Advance to a new concept.

        Args:
            concept_id: The concept to advance to.
        """
        concept = self.curriculum.get_concept(concept_id)
        if concept is None:
            logger.error(f"Concept not found: {concept_id}")
            return

        logger.info(f"Advancing to concept: {concept_id}")

        # Update session state
        self._session_state.advance_concept(concept_id)

        # Update context builder
        self._context_builder.set_concept(concept)

        # Check for concept transition trigger
        trigger = self._student_model.advance_concept(concept_id)
        if trigger:
            self._schedule_brief_generation(trigger)

        # Set up first step
        step = self._session_state.get_current_step()
        if step:
            self._context_builder.set_step(step)
            self._pattern_matcher.set_expected_patterns(step.expected_answers)

    async def _advance_step(self) -> bool:
        """Advance to the next scaffold step.

        Returns:
            True if advanced to a new step, False if concept is complete.
        """
        # Mark revelation as seen if present
        step = self._session_state.get_current_step()
        if step and step.revelation:
            self._context_builder.mark_revelation_seen(step.revelation.pattern_name)

        # Try to advance
        if self._session_state.advance_step():
            new_step = self._session_state.get_current_step()
            if new_step:
                self._context_builder.set_step(new_step)
                self._pattern_matcher.set_expected_patterns(new_step.expected_answers)
                self._context_builder.reset_hints()
                self._hints_given_this_turn = 0
                logger.debug(f"Advanced to step {new_step.step_id}")
                return True

        # Concept complete - move to next in session plan
        return await self._advance_to_next_concept()

    async def _advance_to_next_concept(self) -> bool:
        """Advance to the next concept in the session plan.

        Returns:
            True if advanced to a new concept, False if session is complete.
        """
        self._session_plan_index += 1

        if self._session_plan_index >= len(self._session_plan):
            logger.info("Session plan complete")
            return False

        next_concept_id, is_review = self._session_plan[self._session_plan_index]
        self._last_was_review = is_review

        await self._advance_to_concept(next_concept_id)
        return True

    def _transition_to(self, new_state: OrchestratorState) -> None:
        """Transition to a new state."""
        logger.debug(f"State transition: {self.state.value} -> {new_state.value}")
        self.state = new_state

    async def _start_turn(self) -> None:
        """Start a new turn, pre-computing branches if needed."""
        self._turn_start_time = time.perf_counter()
        self._hints_given_this_turn = 0
        self._context_builder.reset_hints()

        step = self._session_state.get_current_step()
        if step is None:
            return

        # Determine state based on difficulty
        if step.difficulty >= 2:
            self._transition_to(OrchestratorState.THINKING_PAUSE)
            # Push TurnContextFrame to filler engine
            turn_frame = TurnContextFrame(
                difficulty=step.difficulty,
                hints=step.hints,
                evaluation_signal=None,
            )
            await self.push_frame(turn_frame, FrameDirection.DOWNSTREAM)
        else:
            self._transition_to(OrchestratorState.WAITING_FOR_SPEECH)

        # Pre-compute branches for fast path
        await self._precompute_branches()

    async def _precompute_branches(self) -> None:
        """Pre-compute context for both correct and incorrect outcomes."""
        step = self._session_state.get_current_step()
        if step is None:
            return

        # Create match results for each branch
        correct_result = MatchResult(
            signal=MatchSignal.CLEAR_MATCH,
            score=100.0,
            best_match=step.expected_answers[0] if step.expected_answers else "",
            diff=None,
        )

        incorrect_result = MatchResult(
            signal=MatchSignal.CLEAR_MISS,
            score=30.0,
            best_match=step.expected_answers[0] if step.expected_answers else "",
            diff="[precomputed]",
        )

        # Build contexts
        correct_context = self._context_builder.build_turn_context(
            self._session_state,
            match_result=correct_result,
            student_transcript="[correct response]",
        )

        incorrect_context = self._context_builder.build_turn_context(
            self._session_state,
            match_result=incorrect_result,
            student_transcript="[incorrect response]",
        )

        branches = PrecomputedBranches()

        if correct_context:
            branches.correct = PrecomputedBranch(
                context=correct_context,
                system_prompt=self._context_builder.build_system_prompt(correct_context),
            )

        if incorrect_context:
            branches.incorrect = PrecomputedBranch(
                context=incorrect_context,
                system_prompt=self._context_builder.build_system_prompt(incorrect_context),
            )

        self._precomputed = branches
        logger.debug("Pre-computed branches for fast path")

    async def _handle_transcription(self, transcript: str) -> None:
        """Handle a completed transcription from STT.

        Args:
            transcript: The student's transcribed speech.
        """
        self._transition_to(OrchestratorState.EVALUATING)

        # Check for off-script request first
        off_script_type = self._off_script_detector.detect(transcript)
        if off_script_type != OffScriptType.NONE:
            await self._handle_off_script(off_script_type)
            return

        # Evaluate with pattern matcher
        match_result = self._pattern_matcher.match_with_signal(transcript)

        # Calculate response time
        response_time = None
        if self._turn_start_time:
            response_time = time.perf_counter() - self._turn_start_time

        # Select context based on signal
        await self._route_by_signal(match_result, transcript, response_time)

    async def _route_by_signal(
        self,
        match_result: MatchResult,
        transcript: str,
        response_time: float | None,
    ) -> None:
        """Route to appropriate handler based on match signal.

        Args:
            match_result: Result from pattern matcher.
            transcript: Student's transcribed speech.
            response_time: Time taken to respond.
        """
        if match_result.signal == MatchSignal.CLEAR_MATCH:
            await self._handle_correct_response(match_result, transcript, response_time)

        elif match_result.signal == MatchSignal.CLEAR_MISS:
            await self._handle_incorrect_response(match_result, transcript, response_time)

        else:  # AMBIGUOUS
            await self._handle_ambiguous_response(match_result, transcript, response_time)

    async def _handle_correct_response(
        self,
        match_result: MatchResult,
        transcript: str,
        response_time: float | None,
    ) -> None:
        """Handle a correct student response."""
        logger.info(f"Correct response: {transcript[:50]}...")

        # Record to student model
        concept_id = self._session_state.current_concept_id
        if concept_id:
            triggers = self._student_model.record_response(
                concept_id=concept_id,
                correct=True,
                response_time=response_time,
                student_response=transcript,
                expected_response=match_result.best_match or "",
            )
            for trigger in triggers:
                self._schedule_brief_generation(trigger)

        # Record to session state
        self._session_state.record_response(correct=True, response_time=response_time)

        # Use pre-computed branch if available, otherwise build fresh
        context: TurnContext | None = None
        if self._precomputed and self._precomputed.correct:
            context = self._precomputed.correct.context
            # Update with actual transcript
            context.student_transcript = transcript
        else:
            context = self._context_builder.build_turn_context(
                self._session_state,
                match_result=match_result,
                student_transcript=transcript,
            )

        if context:
            context.thinking_pause_hints_given = self._hints_given_this_turn
            await self._generate_response(context)

        # Advance to next step
        await self._advance_step()

    async def _handle_incorrect_response(
        self,
        match_result: MatchResult,
        transcript: str,
        response_time: float | None,
    ) -> None:
        """Handle an incorrect student response."""
        logger.info(f"Incorrect response: {transcript[:50]}... (diff: {match_result.diff})")

        # Record to student model
        concept_id = self._session_state.current_concept_id
        if concept_id:
            triggers = self._student_model.record_response(
                concept_id=concept_id,
                correct=False,
                response_time=response_time,
                error_type=match_result.diff or "unknown",
                student_response=transcript,
                expected_response=match_result.best_match or "",
            )
            for trigger in triggers:
                self._schedule_brief_generation(trigger)

        # Record to session state
        self._session_state.record_response(correct=False, response_time=response_time)

        # Use pre-computed branch if available
        context: TurnContext | None = None
        if self._precomputed and self._precomputed.incorrect:
            context = self._precomputed.incorrect.context
            # Update with actual data
            context.student_transcript = transcript
            context.diff = match_result.diff
            context.match_score = match_result.score
        else:
            context = self._context_builder.build_turn_context(
                self._session_state,
                match_result=match_result,
                student_transcript=transcript,
            )

        if context:
            context.thinking_pause_hints_given = self._hints_given_this_turn
            await self._generate_response(context)

        # Stay on same step for retry

    async def _handle_ambiguous_response(
        self,
        match_result: MatchResult,
        transcript: str,
        response_time: float | None,
    ) -> None:
        """Handle an ambiguous response that needs LLM evaluation."""
        logger.info(f"Ambiguous response: {transcript[:50]}... (score: {match_result.score})")

        # Build fresh context with ambiguous signal - LLM will evaluate inline
        context = self._context_builder.build_turn_context(
            self._session_state,
            match_result=match_result,
            student_transcript=transcript,
        )

        if context:
            context.thinking_pause_hints_given = self._hints_given_this_turn
            await self._generate_response(context)

        # For ambiguous, we don't automatically advance - LLM response determines flow

    async def _handle_off_script(self, off_script_type: OffScriptType) -> None:
        """Handle off-script meta-requests.

        Args:
            off_script_type: Type of off-script request detected.
        """
        logger.info(f"Off-script request: {off_script_type.value}")

        step = self._session_state.get_current_step()
        if step is None:
            return

        # Generate canned response (bypasses LLM for speed)
        response = await self._tutor_agent.generate_off_script_response(
            off_script_type=off_script_type.value,
            current_prompt=step.tutor_prompt,
            hints=step.hints,
            hints_given=self._hints_given_this_turn,
        )

        if off_script_type == OffScriptType.HELP:
            # Track hint given
            self._hints_given_this_turn += 1
            self._context_builder.record_hint_given()

        elif off_script_type == OffScriptType.SKIP:
            # Advance to next step/concept
            await self._advance_step()

        # Push response directly to TTS
        if response:
            self._transition_to(OrchestratorState.SPEAKING)
            await self.push_frame(TextFrame(text=response), FrameDirection.DOWNSTREAM)

    async def _generate_response(self, context: TurnContext) -> None:
        """Generate tutor response via LLM streaming.

        Args:
            context: TurnContext with all information for response generation.
        """
        self._transition_to(OrchestratorState.GENERATING)

        # Push start frame
        await self.push_frame(LLMFullResponseStartFrame(), FrameDirection.DOWNSTREAM)

        # Stream response
        async for chunk in self._tutor_agent.generate_response(context):
            await self.push_frame(LLMTextFrame(text=chunk), FrameDirection.DOWNSTREAM)

        # Push end frame
        await self.push_frame(LLMFullResponseEndFrame(), FrameDirection.DOWNSTREAM)

    def _schedule_brief_generation(self, trigger: TriggerEvent) -> None:
        """Schedule async teaching brief generation.

        Args:
            trigger: The trigger event that caused this.
        """
        async def _generate() -> None:
            try:
                brief = await self._student_model.generate_brief_for_trigger(trigger)
                self._context_builder.set_teaching_brief(brief)
                logger.debug(f"Teaching brief generated for {trigger.trigger_type.value}")
            except Exception as e:
                logger.error(f"Failed to generate teaching brief: {e}")

        task = asyncio.create_task(_generate())
        self._pending_brief_tasks.append(task)

        # Clean up completed tasks
        self._pending_brief_tasks = [t for t in self._pending_brief_tasks if not t.done()]

    async def _handle_hint_delivered(self, frame: HintDeliveredFrame) -> None:
        """Handle notification that a hint was delivered.

        Args:
            frame: HintDeliveredFrame with hint info.
        """
        self._hints_given_this_turn = frame.hint_index + 1
        self._context_builder.record_hint_given()
        logger.debug(f"Hint {frame.hint_index + 1}/{frame.total_hints} delivered")

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        """Process frames based on current state.

        Args:
            frame: The frame to process.
            direction: Frame direction.
        """
        # Handle HintDeliveredFrame from filler engine (upstream)
        if isinstance(frame, HintDeliveredFrame):
            await self._handle_hint_delivered(frame)
            return  # Don't pass upstream

        # Handle transcription frames
        if isinstance(frame, TranscriptionFrame):
            if self.state in (
                OrchestratorState.WAITING_FOR_SPEECH,
                OrchestratorState.THINKING_PAUSE,
            ):
                await self._handle_transcription(frame.text)
            # Pass through for logging/debugging
            await self.push_frame(frame, direction)
            return

        # Handle TTS state changes
        if isinstance(frame, TTSStartedFrame):
            self._transition_to(OrchestratorState.SPEAKING)
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, TTSStoppedFrame):
            # After speaking, start next turn
            await self._start_turn()
            await self.push_frame(frame, direction)
            return

        # Pass all other frames through
        await self.push_frame(frame, direction)

    async def cleanup(self) -> None:
        """Clean up resources and save state."""
        # Wait for pending brief tasks
        if self._pending_brief_tasks:
            await asyncio.gather(*self._pending_brief_tasks, return_exceptions=True)

        # Save student model
        await self._student_model.save()
        logger.info("Session orchestrator cleaned up")


# Legacy alias for backwards compatibility
Orchestrator = SessionOrchestrator
TutorState = OrchestratorState
