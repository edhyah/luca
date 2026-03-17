"""Session planner for structuring tutoring sessions."""

from dataclasses import dataclass, field

from luca.curriculum.engine import CurriculumEngine
from luca.student.model import StudentModel
from luca.utils.logging import get_logger

logger = get_logger("curriculum.session_planner")


@dataclass
class SessionPlan:
    """Plan for a tutoring session."""

    concepts: list[str] = field(default_factory=list)
    review_concepts: list[str] = field(default_factory=list)
    target_duration: int = 20  # minutes
    focus_area: str = ""


class SessionPlanner:
    """Plans tutoring sessions based on student state and curriculum."""

    def __init__(
        self,
        curriculum: CurriculumEngine,
        target_session_duration: int = 20,
    ) -> None:
        self.curriculum = curriculum
        self.target_duration = target_session_duration

    async def create_plan(self, student: StudentModel) -> SessionPlan:
        """Create a session plan for the student."""
        mastered = set(student.get_ready_concepts())

        # Get available concepts
        available = self.curriculum.get_available_concepts(mastered)

        # Select concepts for this session
        # TODO: Implement smarter selection based on:
        # - Teaching brief preferences
        # - Time estimates per concept
        # - Spaced repetition for review

        plan = SessionPlan(
            concepts=available[:3],  # Aim for ~3 new concepts
            review_concepts=[],  # TODO: Select concepts for spaced review
            target_duration=self.target_duration,
        )

        logger.info(f"Created session plan with {len(plan.concepts)} concepts")
        return plan

    def should_review(self, concept_id: str, student: StudentModel) -> bool:
        """Determine if a concept should be reviewed."""
        mastery = student.get_mastery(concept_id)
        # Review if mastery has decayed below threshold
        return 0.5 < mastery < 0.8
