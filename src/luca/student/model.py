"""Student model combining BKT, error tracking, and teaching briefs."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from luca.persistence.student_store import StudentStore
from luca.student.bkt import BKTModel
from luca.student.error_tracker import ErrorTracker
from luca.student.session_state import SlidingWindowStats
from luca.student.teaching_brief import TeachingBrief, generate_teaching_brief
from luca.student.triggers import TriggerDetector, TriggerEvent, TriggerType
from luca.utils.logging import get_logger

if TYPE_CHECKING:
    from luca.curriculum.models import Curriculum

logger = get_logger("student.model")


class StudentModel:
    """Unified student model for tracking knowledge, errors, and preferences.

    Combines:
    - BKT with forgetting for mastery tracking
    - Error pattern tracking for detecting repeated mistakes
    - Trigger detection for state changes
    - Teaching brief generation on triggers
    """

    # Maximum number of teaching briefs to keep
    MAX_BRIEFS = 3

    def __init__(self, student_id: str, curriculum: Curriculum | None = None) -> None:
        self.student_id = student_id
        self.curriculum = curriculum

        # Core components
        self.bkt = BKTModel()
        self.error_tracker = ErrorTracker()
        self.trigger_detector = TriggerDetector()
        self.sliding_window = SlidingWindowStats()

        # State
        self.current_concept_id: str | None = None
        self.session_history: list[dict[str, Any]] = []
        self.teaching_briefs: list[TeachingBrief] = []
        self._last_practiced: dict[str, datetime] = {}

        # Initialize BKT with curriculum parameters
        if curriculum:
            self._init_bkt_from_curriculum()

        # Persistence
        self._store = StudentStore()

    def _init_bkt_from_curriculum(self) -> None:
        """Initialize BKT parameters from curriculum."""
        if not self.curriculum:
            return
        for concept in self.curriculum.concepts:
            self.bkt.set_params(concept.concept_id, concept.bkt_parameters)

    async def load(self) -> None:
        """Load student data from persistence and apply decay.

        Loads mastery records from DB and applies time-based decay
        based on hours since last_practiced.
        """
        logger.info(f"Loading student model for {self.student_id}")

        # Load mastery records
        mastery_records = await self._store.get_all_mastery(self.student_id)
        now = datetime.now(timezone.utc)

        for record in mastery_records:
            concept_id = record.concept_id

            # Set mastery
            self.bkt.set_mastery(concept_id, record.mastery)

            # Load BKT params if customized
            if record.bkt_params:
                self.bkt.params[concept_id] = record.bkt_params

            # Apply decay based on time since last practice
            if record.last_practiced:
                last_practiced = record.last_practiced
                if last_practiced.tzinfo is None:
                    last_practiced = last_practiced.replace(tzinfo=timezone.utc)

                hours_elapsed = (now - last_practiced).total_seconds() / 3600
                if hours_elapsed > 0:
                    old_mastery = self.bkt.get_mastery(concept_id)
                    new_mastery = self.bkt.apply_decay(concept_id, hours_elapsed)
                    logger.debug(
                        f"Applied decay to {concept_id}: {old_mastery:.3f} -> {new_mastery:.3f} "
                        f"({hours_elapsed:.1f} hours)"
                    )

                self._last_practiced[concept_id] = last_practiced

            # Mark concept as visited for trigger detection
            self.trigger_detector.mark_concept_visited(concept_id)
            self.trigger_detector.update_prev_mastery(concept_id, self.bkt.get_mastery(concept_id))

        # Load teaching brief
        brief = await self._store.get_teaching_brief(self.student_id)
        if brief:
            self.teaching_briefs.append(brief)

        logger.info(
            f"Loaded {len(mastery_records)} mastery records, "
            f"{len(self.teaching_briefs)} briefs"
        )

    async def save(self) -> None:
        """Save student data to persistence."""
        logger.info(f"Saving student model for {self.student_id}")

        # Save mastery records
        for concept_id, mastery in self.bkt.mastery.items():
            # Get last response for this concept from session history
            last_correct = None
            for entry in reversed(self.session_history):
                if entry.get("concept_id") == concept_id:
                    last_correct = entry.get("correct", True)
                    break

            if last_correct is not None:
                await self._store.update_mastery(
                    self.student_id, concept_id, mastery, last_correct
                )

        # Save latest teaching brief
        if self.teaching_briefs:
            await self._store.save_teaching_brief(
                self.student_id, self.teaching_briefs[-1]
            )

        logger.info(f"Saved {len(self.bkt.mastery)} mastery records")

    def record_response(
        self,
        concept_id: str,
        correct: bool,
        response_time: float | None = None,
        error_type: str | None = None,
        student_response: str = "",
        expected_response: str = "",
    ) -> list[TriggerEvent]:
        """Record a student response and check for triggers.

        Args:
            concept_id: The concept being practiced.
            correct: Whether the response was correct.
            response_time: Time to respond in seconds.
            error_type: Type of error if incorrect.
            student_response: What the student said.
            expected_response: What was expected.

        Returns:
            List of trigger events that fired.
        """
        triggers: list[TriggerEvent] = []
        actual_time = response_time if response_time is not None else 0.0

        # Get old values for trigger detection
        old_mastery = self.bkt.get_mastery(concept_id)
        old_avg_time = self.trigger_detector.get_prev_response_time(concept_id) or 0.0

        # Update BKT
        new_mastery = self.bkt.update(concept_id, correct)

        # Update sliding window
        self.sliding_window.add_response(correct, actual_time)

        # Record to session history
        self.session_history.append({
            "concept_id": concept_id,
            "correct": correct,
            "response_time": int(actual_time * 1000) if actual_time else None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        # Track errors
        if not correct and error_type:
            triggered = self.error_tracker.record_error(
                error_type=error_type,
                concept_id=concept_id,
                student_response=student_response,
                expected_response=expected_response,
            )
            if triggered:
                triggers.append(TriggerEvent(
                    trigger_type=TriggerType.ERROR_PATTERN,
                    concept_id=concept_id,
                    details={
                        "error_type": error_type,
                        "count": self.error_tracker.get_pattern(error_type, concept_id).count  # type: ignore
                    },
                ))

        # Check mastery threshold
        mastery_trigger = self.trigger_detector.check_mastery_threshold(
            concept_id, old_mastery, new_mastery
        )
        if mastery_trigger:
            triggers.append(mastery_trigger)

        # Check response speed (need enough data)
        if self.sliding_window.response_count >= 5 and actual_time > 0:
            new_avg_time = self.sliding_window.avg_response_time
            if old_avg_time > 0:
                speed_trigger = self.trigger_detector.check_response_speed(
                    concept_id, old_avg_time, new_avg_time
                )
                if speed_trigger:
                    triggers.append(speed_trigger)
            self.trigger_detector.update_prev_response_time(concept_id, new_avg_time)

        # Update tracked values
        self.trigger_detector.update_prev_mastery(concept_id, new_mastery)
        self._last_practiced[concept_id] = datetime.now(timezone.utc)

        return triggers

    def advance_concept(self, new_concept_id: str) -> TriggerEvent | None:
        """Advance to a new concept and check for transition trigger.

        Args:
            new_concept_id: The concept to advance to.

        Returns:
            A concept transition trigger if this is a new concept.
        """
        old_concept_id = self.current_concept_id
        self.current_concept_id = new_concept_id

        return self.trigger_detector.check_concept_transition(
            old_concept_id, new_concept_id
        )

    async def generate_brief_for_trigger(
        self, trigger_event: TriggerEvent
    ) -> TeachingBrief:
        """Generate a teaching brief for a trigger event.

        Calls Gemini Flash to analyze session history and generate
        actionable insights. Keeps only the last MAX_BRIEFS briefs.

        Args:
            trigger_event: The trigger that caused this brief generation.

        Returns:
            The generated TeachingBrief.
        """
        logger.info(
            f"Generating brief for trigger {trigger_event.trigger_type.value} "
            f"on {trigger_event.concept_id}"
        )

        # Gather context
        mastery_levels = dict(self.bkt.mastery)
        sliding_stats = {
            "error_rate": self.sliding_window.error_rate,
            "avg_response_time": self.sliding_window.avg_response_time,
            "streak_length": self.sliding_window.streak_length,
            "response_count": self.sliding_window.response_count,
        }

        # Generate brief
        brief = await generate_teaching_brief(
            student_id=self.student_id,
            session_history=self.session_history,
            error_patterns=self.error_tracker.get_triggered_patterns(),
            mastery_levels=mastery_levels,
            sliding_window_stats=sliding_stats,
            trigger_event=trigger_event,
        )

        # Add to list and trim
        self.teaching_briefs.append(brief)
        if len(self.teaching_briefs) > self.MAX_BRIEFS:
            self.teaching_briefs = self.teaching_briefs[-self.MAX_BRIEFS:]

        return brief

    def get_mastery(self, concept_id: str) -> float:
        """Get the mastery probability for a concept."""
        return self.bkt.get_mastery(concept_id)

    def get_all_mastery(self) -> dict[str, float]:
        """Get mastery probabilities for all concepts."""
        return dict(self.bkt.mastery)

    def get_ready_concepts(self, threshold: float = 0.8) -> list[str]:
        """Get concepts that are considered mastered."""
        return self.bkt.get_mastered_concepts(threshold)

    def get_latest_brief(self) -> TeachingBrief | None:
        """Get the most recent teaching brief."""
        return self.teaching_briefs[-1] if self.teaching_briefs else None

    def get_sliding_stats(self) -> dict[str, Any]:
        """Get current sliding window statistics."""
        return {
            "error_rate": self.sliding_window.error_rate,
            "avg_response_time": self.sliding_window.avg_response_time,
            "streak_length": self.sliding_window.streak_length,
            "response_count": self.sliding_window.response_count,
        }
