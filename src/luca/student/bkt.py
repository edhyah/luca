"""Bayesian Knowledge Tracing implementation."""

from luca.utils.logging import get_logger

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
    }

    def __init__(self) -> None:
        # Mastery probabilities per concept
        self.mastery: dict[str, float] = {}
        # Parameters per concept (can be learned or set)
        self.params: dict[str, dict[str, float]] = {}

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
