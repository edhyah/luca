"""Bayesian Knowledge Tracing implementation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from luca.utils.logging import get_logger

if TYPE_CHECKING:
    from luca.curriculum.models import BKTParameters

logger = get_logger("student.bkt")


class BKTModel:
    """Bayesian Knowledge Tracing for student mastery estimation.

    Uses pyBKT under the hood but provides a simplified interface.
    """

    # Default BKT parameters
    DEFAULT_PARAMS = {
        "p_init": 0.1,  # Prior probability of knowing skill
        "p_learn": 0.2,  # Probability of learning after opportunity
        "p_guess": 0.25,  # Probability of guessing correctly
        "p_slip": 0.1,  # Probability of slipping (knowing but wrong)
        "p_forget": 0.05,  # Probability of forgetting per day
    }

    def __init__(self) -> None:
        # Mastery probabilities per concept
        self.mastery: dict[str, float] = {}
        # Parameters per concept (can be learned or set)
        self.params: dict[str, dict[str, float]] = {}

    def set_params(self, concept_id: str, bkt_params: BKTParameters) -> None:
        """Set BKT parameters for a concept from a BKTParameters model."""
        self.params[concept_id] = {
            "p_init": bkt_params.p_init,
            "p_learn": bkt_params.p_learn,
            "p_guess": bkt_params.p_guess,
            "p_slip": bkt_params.p_slip,
            "p_forget": bkt_params.p_forget,
        }

    def get_params(self, concept_id: str) -> dict[str, float]:
        """Get BKT parameters for a concept."""
        return self.params.get(concept_id, self.DEFAULT_PARAMS.copy())

    def update(self, concept_id: str, correct: bool) -> float:
        """Update mastery estimate after a response.

        Returns the new mastery probability.
        """
        params = self.get_params(concept_id)
        p_know = self.mastery.get(concept_id, params["p_init"])

        # Calculate P(correct | know) and P(correct | ~know)
        p_correct_given_know = 1 - params["p_slip"]
        p_correct_given_not_know = params["p_guess"]

        # Posterior probability of knowing given response
        if correct:
            p_know_posterior = (p_correct_given_know * p_know) / (
                p_correct_given_know * p_know
                + p_correct_given_not_know * (1 - p_know)
            )
        else:
            p_know_posterior = (params["p_slip"] * p_know) / (
                params["p_slip"] * p_know + (1 - params["p_guess"]) * (1 - p_know)
            )

        # Apply learning (transition probability)
        new_mastery = p_know_posterior + (1 - p_know_posterior) * params["p_learn"]

        self.mastery[concept_id] = new_mastery
        logger.debug(f"BKT update for {concept_id}: {p_know:.3f} -> {new_mastery:.3f}")

        return new_mastery

    def get_mastery(self, concept_id: str) -> float:
        """Get current mastery probability for a concept."""
        params = self.get_params(concept_id)
        return self.mastery.get(concept_id, params["p_init"])

    def get_mastered_concepts(self, threshold: float = 0.8) -> list[str]:
        """Get list of concepts above mastery threshold."""
        return [cid for cid, m in self.mastery.items() if m >= threshold]

    def apply_decay(self, concept_id: str, hours_elapsed: float) -> float:
        """Apply forgetting decay to a concept's mastery.

        Decay formula: new = old * (1 - p_forget) ^ (hours / 24)

        Args:
            concept_id: The concept to apply decay to.
            hours_elapsed: Hours since last practice.

        Returns:
            The new mastery probability after decay.
        """
        if concept_id not in self.mastery:
            return self.get_mastery(concept_id)

        params = self.get_params(concept_id)
        p_forget: float = params.get("p_forget", 0.0)

        if p_forget <= 0 or hours_elapsed <= 0:
            return self.mastery[concept_id]

        old_mastery = self.mastery[concept_id]
        days_elapsed = hours_elapsed / 24.0
        decay_factor = (1 - p_forget) ** days_elapsed
        p_init: float = params["p_init"]
        new_mastery: float = max(p_init, old_mastery * decay_factor)

        self.mastery[concept_id] = new_mastery
        logger.debug(
            f"BKT decay for {concept_id}: {old_mastery:.3f} -> {new_mastery:.3f} "
            f"(hours={hours_elapsed:.1f}, p_forget={p_forget})"
        )

        return new_mastery

    def set_mastery(self, concept_id: str, mastery: float) -> None:
        """Set mastery probability directly (used when loading from persistence)."""
        self.mastery[concept_id] = max(0.0, min(1.0, mastery))
