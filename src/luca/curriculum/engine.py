"""Curriculum engine for managing lesson progression."""

from __future__ import annotations

from luca.curriculum.loader import CurriculumLoader
from luca.curriculum.models import Concept, Curriculum, ScaffoldStep
from luca.utils.logging import get_logger

logger = get_logger("curriculum.engine")

# Mastery thresholds
UNLOCK_THRESHOLD = 0.7  # Prerequisites must reach this to unlock new concepts
REVIEW_THRESHOLD = 0.5  # Below this triggers review
STRONG_THRESHOLD = 0.8  # Above this is "strong"


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

    def get_mastered_set(
        self, mastery: dict[str, float], threshold: float = UNLOCK_THRESHOLD
    ) -> set[str]:
        """Convert mastery dict to set of mastered concept IDs.

        Args:
            mastery: Dict mapping concept_id to mastery probability.
            threshold: Minimum mastery to be considered "mastered".

        Returns:
            Set of concept IDs that meet the threshold.
        """
        return {cid for cid, m in mastery.items() if m >= threshold}

    def get_review_candidates(
        self,
        mastery: dict[str, float],
        threshold: float = REVIEW_THRESHOLD,
    ) -> list[tuple[str, float]]:
        """Get concepts that need review (mastery below threshold).

        Only includes concepts that have been practiced (exist in mastery dict).

        Args:
            mastery: Dict mapping concept_id to mastery probability.
            threshold: Concepts below this mastery level need review.

        Returns:
            List of (concept_id, mastery) sorted by mastery ascending.
        """
        candidates = [
            (cid, m)
            for cid, m in mastery.items()
            if m < threshold
        ]
        # Sort by mastery ascending (most decayed first)
        candidates.sort(key=lambda x: x[1])
        return candidates

    def get_next_concept(
        self,
        mastery: dict[str, float],
        current_concept_id: str | None = None,
        last_was_review: bool = False,
    ) -> tuple[str | None, bool]:
        """Get next concept, weaving in review as needed.

        Args:
            mastery: Dict mapping concept_id to mastery probability.
            current_concept_id: Current concept being worked on (excluded).
            last_was_review: Whether the last concept was a review.

        Returns:
            Tuple of (concept_id, is_review). Returns (None, False) if nothing available.

        Logic:
        - If last was NOT review, check for review candidates first
        - Otherwise, prefer new material if available
        - Falls back to whatever is available
        """
        mastered_set = self.get_mastered_set(mastery)
        available_new = self.get_available_concepts(mastered_set)

        # Exclude current concept from new material
        if current_concept_id and current_concept_id in available_new:
            available_new.remove(current_concept_id)

        # Get review candidates, excluding current concept
        review_candidates = self.get_review_candidates(mastery)
        if current_concept_id:
            review_candidates = [
                (cid, m) for cid, m in review_candidates if cid != current_concept_id
            ]

        has_new = len(available_new) > 0
        has_review = len(review_candidates) > 0

        # Weaving logic: alternate between review and new
        if not last_was_review and has_review:
            # Last was new, so try review next
            return (review_candidates[0][0], True)
        elif has_new:
            # Prefer new material
            return (available_new[0], False)
        elif has_review:
            # Fall back to review
            return (review_candidates[0][0], True)
        else:
            # Nothing available
            return (None, False)

    def plan_session(
        self,
        mastery: dict[str, float],
        max_concepts: int = 5,
    ) -> list[tuple[str, bool]]:
        """Plan a session sequence.

        Args:
            mastery: Dict mapping concept_id to mastery probability.
            max_concepts: Maximum number of concepts to include in the session.

        Returns:
            List of (concept_id, is_review) tuples.

        Strategy:
        1. Start with most-decayed review concept (if any)
        2. Alternate between review and new material
        3. End with a strong concept (mastery >= STRONG_THRESHOLD)
        """
        if max_concepts <= 0:
            return []

        planned: list[tuple[str, bool]] = []
        used_concepts: set[str] = set()

        # Working copy of mastery that we'll update as we "use" concepts
        mastered_set = self.get_mastered_set(mastery)
        available_new = [c for c in self.get_available_concepts(mastered_set)]
        review_candidates = self.get_review_candidates(mastery)

        # Get strong concepts for ending
        strong_concepts = [
            cid for cid, m in mastery.items() if m >= STRONG_THRESHOLD
        ]

        # Start with most-decayed review concept if available
        last_was_review = False
        if review_candidates:
            most_decayed = review_candidates[0][0]
            planned.append((most_decayed, True))
            used_concepts.add(most_decayed)
            last_was_review = True

        # Build middle of session, alternating review and new
        while len(planned) < max_concepts:
            # Filter out already-used concepts
            remaining_new = [c for c in available_new if c not in used_concepts]
            remaining_review = [
                (cid, m) for cid, m in review_candidates if cid not in used_concepts
            ]

            has_new = len(remaining_new) > 0
            has_review = len(remaining_review) > 0

            if not has_new and not has_review:
                break

            # Alternate: if last was review, try new; otherwise try review
            if last_was_review and has_new:
                concept = remaining_new[0]
                planned.append((concept, False))
                used_concepts.add(concept)
                last_was_review = False
            elif not last_was_review and has_review:
                concept = remaining_review[0][0]
                planned.append((concept, True))
                used_concepts.add(concept)
                last_was_review = True
            elif has_new:
                concept = remaining_new[0]
                planned.append((concept, False))
                used_concepts.add(concept)
                last_was_review = False
            else:
                concept = remaining_review[0][0]
                planned.append((concept, True))
                used_concepts.add(concept)
                last_was_review = True

        # Try to end with a strong concept if we have room and one isn't already last
        if planned and len(planned) < max_concepts:
            # Check if last concept is already strong
            last_concept = planned[-1][0]
            if mastery.get(last_concept, 0) < STRONG_THRESHOLD:
                # Find a strong concept we haven't used
                for strong in strong_concepts:
                    if strong not in used_concepts:
                        # Add as review (since it's a concept they've mastered)
                        planned.append((strong, True))
                        break

        return planned
