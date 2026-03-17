"""Student model combining BKT and teaching briefs."""

from luca.student.bkt import BKTModel
from luca.student.teaching_brief import TeachingBrief
from luca.utils.logging import get_logger

logger = get_logger("student.model")


class StudentModel:
    """Unified student model for tracking knowledge and preferences."""

    def __init__(self, student_id: str) -> None:
        self.student_id = student_id
        self.bkt = BKTModel()
        self.teaching_brief: TeachingBrief | None = None
        self.session_history: list[dict] = []

    async def load(self) -> None:
        """Load student data from persistence."""
        # TODO: Load from database
        pass

    async def save(self) -> None:
        """Save student data to persistence."""
        # TODO: Save to database
        pass

    def record_response(
        self,
        concept_id: str,
        correct: bool,
        response_time: float | None = None,
    ) -> None:
        """Record a student response for a concept."""
        self.bkt.update(concept_id, correct)
        self.session_history.append({
            "concept_id": concept_id,
            "correct": correct,
            "response_time": response_time,
        })

    def get_mastery(self, concept_id: str) -> float:
        """Get the mastery probability for a concept."""
        return self.bkt.get_mastery(concept_id)

    def get_ready_concepts(self, threshold: float = 0.8) -> list[str]:
        """Get concepts that are ready to be considered mastered."""
        return self.bkt.get_mastered_concepts(threshold)
