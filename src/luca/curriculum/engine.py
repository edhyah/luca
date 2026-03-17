"""Curriculum engine for managing lesson progression."""

from luca.curriculum.loader import CurriculumLoader
from luca.utils.logging import get_logger

logger = get_logger("curriculum.engine")


class CurriculumEngine:
    """Manages curriculum state and concept progression."""

    def __init__(self, loader: CurriculumLoader | None = None) -> None:
        self.loader = loader or CurriculumLoader()
        self.concepts: dict[str, dict] = {}
        self.dag: dict[str, list[str]] = {}  # concept_id -> prerequisite_ids

    async def load_curriculum(self, curriculum_path: str = "curriculum") -> None:
        """Load curriculum data from the specified path."""
        self.dag = await self.loader.load_dag(f"{curriculum_path}/dag.json")
        self.concepts = await self.loader.load_concepts(f"{curriculum_path}/concepts")
        logger.info(f"Loaded {len(self.concepts)} concepts")

    def get_concept(self, concept_id: str) -> dict | None:
        """Get a concept by ID."""
        return self.concepts.get(concept_id)

    def get_prerequisites(self, concept_id: str) -> list[str]:
        """Get prerequisite concept IDs for a concept."""
        return self.dag.get(concept_id, [])

    def get_available_concepts(self, mastered: set[str]) -> list[str]:
        """Get concepts whose prerequisites are all mastered."""
        available = []
        for concept_id, prereqs in self.dag.items():
            if concept_id not in mastered:
                if all(p in mastered for p in prereqs):
                    available.append(concept_id)
        return available

    def get_next_concept(
        self,
        mastered: set[str],
        current_focus: str | None = None,
    ) -> str | None:
        """Get the next recommended concept to teach."""
        available = self.get_available_concepts(mastered)

        if not available:
            return None

        # Simple heuristic: prefer concepts that unlock more downstream concepts
        # TODO: Implement more sophisticated selection
        return available[0]
