"""Curriculum data loader."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from luca.utils.logging import get_logger

if TYPE_CHECKING:
    from luca.curriculum.models import Curriculum

logger = get_logger("curriculum.loader")


class CurriculumLoader:
    """Loads curriculum data from JSON files."""

    def __init__(self, base_path: str = "curriculum") -> None:
        self.base_path = Path(base_path)

    async def load_dag(self, path: str) -> dict[str, list[str]]:
        """Load the curriculum DAG from JSON."""
        dag_path = Path(path)
        if not dag_path.exists():
            logger.warning(f"DAG file not found: {path}")
            return {}

        with open(dag_path) as f:
            data = json.load(f)

        # Expected format: {"nodes": [...], "edges": [...]}
        # or simplified: {"concept_id": ["prereq1", "prereq2"], ...}
        if "edges" in data:
            dag: dict[str, list[str]] = {}
            for edge in data["edges"]:
                target = edge["target"]
                source = edge["source"]
                if target not in dag:
                    dag[target] = []
                dag[target].append(source)
            return dag

        return data

    async def load_concepts(self, concepts_dir: str) -> dict[str, dict]:
        """Load all concept definitions from a directory."""
        concepts_path = Path(concepts_dir)
        if not concepts_path.exists():
            logger.warning(f"Concepts directory not found: {concepts_dir}")
            return {}

        concepts = {}
        for concept_file in concepts_path.glob("*.json"):
            if concept_file.name.startswith("_"):
                continue  # Skip templates

            with open(concept_file) as f:
                concept = json.load(f)
                concept_id = concept.get("id", concept_file.stem)
                concepts[concept_id] = concept

        logger.info(f"Loaded {len(concepts)} concepts from {concepts_dir}")
        return concepts

    async def load_concept(self, concept_id: str) -> dict | None:
        """Load a single concept by ID."""
        concept_path = self.base_path / "concepts" / f"{concept_id}.json"
        if not concept_path.exists():
            return None

        with open(concept_path) as f:
            return json.load(f)

    def load_curriculum(self, path: str) -> Curriculum:
        """Load a unified curriculum JSON file.

        Args:
            path: Path to the curriculum JSON file (e.g., 'data/curriculum.json')

        Returns:
            Validated Curriculum model
        """
        from luca.curriculum.models import Curriculum

        curriculum_path = Path(path)
        if not curriculum_path.exists():
            raise FileNotFoundError(f"Curriculum file not found: {path}")

        with open(curriculum_path) as f:
            data = json.load(f)

        curriculum = Curriculum.model_validate(data)
        logger.info(
            f"Loaded curriculum v{curriculum.version} with {len(curriculum.concepts)} concepts"
        )
        return curriculum
