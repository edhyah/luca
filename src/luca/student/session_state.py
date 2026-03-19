"""Session state tracking for a single tutoring session."""

from collections import deque
from dataclasses import dataclass, field
from time import time

from luca.curriculum.models import BKTParameters, Concept, Curriculum, ScaffoldStep
from luca.student.bkt import BKTModel


@dataclass
class SlidingWindowStats:
    """Statistics computed over a sliding window of recent responses."""

    window_size: int = 10
    recent_responses: deque[tuple[bool, float]] = field(
        default_factory=lambda: deque(maxlen=10)
    )

    def __post_init__(self) -> None:
        # Ensure maxlen is set correctly
        if not isinstance(self.recent_responses, deque) or self.recent_responses.maxlen != self.window_size:
            self.recent_responses = deque(maxlen=self.window_size)

    def add_response(self, correct: bool, response_time: float) -> None:
        """Add a response to the sliding window."""
        self.recent_responses.append((correct, response_time))

    @property
    def streak_length(self) -> int:
        """Get the current streak of correct answers."""
        streak = 0
        for correct, _ in reversed(self.recent_responses):
            if correct:
                streak += 1
            else:
                break
        return streak

    @property
    def error_rate(self) -> float:
        """Get the error rate over the window."""
        if not self.recent_responses:
            return 0.0
        errors = sum(1 for correct, _ in self.recent_responses if not correct)
        return errors / len(self.recent_responses)

    @property
    def avg_response_time(self) -> float:
        """Get the average response time over the window."""
        if not self.recent_responses:
            return 0.0
        return sum(t for _, t in self.recent_responses) / len(self.recent_responses)

    @property
    def response_count(self) -> int:
        """Get the number of responses in the window."""
        return len(self.recent_responses)


class SessionState:
    """Tracks state for a single tutoring session.

    Each session starts fresh (no cross-session persistence).
    """

    def __init__(
        self,
        student_id: str,
        curriculum: Curriculum | None = None,
        window_size: int = 10,
    ) -> None:
        self.student_id = student_id
        self.curriculum = curriculum
        self.current_concept_id: str | None = None
        self.current_step_index: int = 0
        self.bkt = BKTModel()
        self.sliding_window = SlidingWindowStats(window_size=window_size)
        self.teaching_briefs: list[str] = []
        self._session_start = time()

        # Initialize BKT with curriculum parameters if available
        if curriculum:
            self._init_bkt_from_curriculum()

    def _init_bkt_from_curriculum(self) -> None:
        """Initialize BKT parameters from curriculum."""
        if not self.curriculum:
            return
        for concept in self.curriculum.concepts:
            self.bkt.set_params(concept.concept_id, concept.bkt_parameters)

    def record_response(
        self,
        correct: bool,
        response_time: float | None = None,
    ) -> float | None:
        """Record a response for the current concept.

        Updates both sliding window stats and BKT mastery.
        Returns the new mastery probability, or None if no concept is active.
        """
        if self.current_concept_id is None:
            return None

        actual_time = response_time if response_time is not None else 0.0
        self.sliding_window.add_response(correct, actual_time)
        new_mastery = self.bkt.update(self.current_concept_id, correct)
        return new_mastery

    def advance_step(self) -> bool:
        """Advance to the next scaffold step.

        Returns True if advanced, False if at the end of the concept.
        """
        if self.current_concept_id is None:
            return False

        concept = self._get_current_concept()
        if concept is None:
            return False

        if self.current_step_index < len(concept.scaffold_steps) - 1:
            self.current_step_index += 1
            return True
        return False

    def advance_concept(self, concept_id: str) -> None:
        """Advance to a new concept."""
        self.current_concept_id = concept_id
        self.current_step_index = 0

    def _get_current_concept(self) -> Concept | None:
        """Get the current concept from the curriculum."""
        if self.curriculum is None or self.current_concept_id is None:
            return None
        return self.curriculum.get_concept(self.current_concept_id)

    def get_current_step(self) -> ScaffoldStep | None:
        """Get the current scaffold step."""
        concept = self._get_current_concept()
        if concept is None:
            return None
        if self.current_step_index >= len(concept.scaffold_steps):
            return None
        return concept.scaffold_steps[self.current_step_index]

    def get_streak(self) -> int:
        """Get the current streak of correct answers."""
        return self.sliding_window.streak_length

    def get_error_rate(self) -> float:
        """Get the error rate over the sliding window."""
        return self.sliding_window.error_rate

    def get_mastery(self, concept_id: str) -> float:
        """Get the current mastery probability for a concept."""
        return self.bkt.get_mastery(concept_id)

    def get_all_mastery(self) -> dict[str, float]:
        """Get mastery probabilities for all concepts with updates."""
        return dict(self.bkt.mastery)

    def get_mastered_concepts(self, threshold: float = 0.8) -> list[str]:
        """Get list of concepts above the mastery threshold."""
        return self.bkt.get_mastered_concepts(threshold)

    def add_teaching_brief(self, brief: str) -> None:
        """Add a teaching brief observed during this session."""
        if brief not in self.teaching_briefs:
            self.teaching_briefs.append(brief)

    def is_concept_complete(self) -> bool:
        """Check if the current concept's scaffold steps are complete."""
        concept = self._get_current_concept()
        if concept is None:
            return True
        return self.current_step_index >= len(concept.scaffold_steps) - 1

    @property
    def session_duration(self) -> float:
        """Get the duration of this session in seconds."""
        return time() - self._session_start
