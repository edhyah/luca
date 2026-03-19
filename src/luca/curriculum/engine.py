"""Curriculum engine for managing lesson progression."""

from __future__ import annotations

from luca.curriculum.loader import CurriculumLoader
from luca.curriculum.models import Concept, Curriculum, ScaffoldStep
from luca.utils.logging import get_logger

logger = get_logger("curriculum.engine")


class CurriculumEngine:
    """Manages curriculum state and concept progression."""

    def __init__(self, loader: CurriculumLoader | None = None) -> None:
        self.loader = loader or CurriculumLoader()
        self.curriculum: Curriculum | None = None
        self.dag: dict[str, list[str]] = {}  # concept_id -> prerequisite_ids

    async def load_curriculum_legacy(self, curriculum_path: str = "curriculum") -> None:
        """Load curriculum data from the legacy directory structure.

        This loads from separate dag.json and concepts/*.json files.
        """
        self.dag = await self.loader.load_dag(f"{curriculum_path}/dag.json")
        concepts = await self.loader.load_concepts(f"{curriculum_path}/concepts")
        logger.info(f"Loaded {len(concepts)} concepts (legacy format)")

    def load_curriculum(self, path: str = "data/curriculum.json") -> Curriculum:
        """Load curriculum from a unified JSON file.

        Args:
            path: Path to the curriculum JSON file

        Returns:
            The loaded Curriculum model
        """
        self.curriculum = self.loader.load_curriculum(path)
        self.dag = self.curriculum.build_dag()
        logger.info(f"Loaded curriculum with {len(self.curriculum.concepts)} concepts")
        return self.curriculum

    def get_concept(self, concept_id: str) -> Concept | None:
        """Get a concept by ID."""
        if self.curriculum is None:
            return None
        return self.curriculum.get_concept(concept_id)

    def get_scaffold_step(self, concept_id: str, step_index: int) -> ScaffoldStep | None:
        """Get a specific scaffold step for a concept.

        Args:
            concept_id: The concept ID
            step_index: Zero-based index of the step

        Returns:
            The ScaffoldStep or None if not found
        """
        concept = self.get_concept(concept_id)
        if concept is None:
            return None
        if step_index < 0 or step_index >= len(concept.scaffold_steps):
            return None
        return concept.scaffold_steps[step_index]

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
