"""Pydantic models for curriculum structure."""

from pydantic import BaseModel, Field


class BKTParameters(BaseModel):
    """Bayesian Knowledge Tracing parameters for a concept."""

    p_init: float = Field(ge=0, le=1, description="Prior probability of knowing skill")
    p_learn: float = Field(ge=0, le=1, description="Probability of learning after opportunity")
    p_guess: float = Field(ge=0, le=1, description="Probability of guessing correctly")
    p_slip: float = Field(ge=0, le=1, description="Probability of slipping (knowing but wrong)")
    p_forget: float = Field(ge=0, le=1, default=0.0, description="Probability of forgetting")


class Revelation(BaseModel):
    """Pattern revelation shown after a scaffold step."""

    pattern_name: str = Field(description="Name of the pattern being revealed")
    first_encounter_script: str = Field(description="Script for first time seeing this pattern")
    review_reference: str = Field(description="Brief reference for review encounters")


class CommonError(BaseModel):
    """Common student error for a concept."""

    error_type: str = Field(description="Type identifier for the error")
    example: str = Field(description="Example of the error")
    explanation: str = Field(description="Why students make this error")
    tutor_correction_approach: str = Field(description="How the tutor should correct this error")


class ScaffoldStep(BaseModel):
    """A single step in a concept's scaffold sequence."""

    step_id: str = Field(description="Unique identifier for this step")
    tutor_prompt: str = Field(description="What the tutor says to prompt the student")
    expected_answers: list[str] = Field(description="Acceptable answers")
    answer_notes: str = Field(default="", description="Notes for evaluating answers")
    difficulty: int = Field(ge=1, le=5, default=2, description="Difficulty level 1-5")
    hints: list[str] = Field(default_factory=list, description="Progressive hints")
    revelation: Revelation | None = Field(default=None, description="Pattern to reveal after this step")


class Concept(BaseModel):
    """A teachable concept in the curriculum."""

    concept_id: str = Field(description="Unique identifier")
    name: str = Field(description="Human-readable name")
    episode: int = Field(description="Episode number this concept belongs to")
    prerequisites: list[str] = Field(default_factory=list, description="Prerequisite concept IDs")
    scaffold_steps: list[ScaffoldStep] = Field(default_factory=list, description="Ordered teaching steps")
    common_errors: list[CommonError] = Field(default_factory=list, description="Common student errors")
    bkt_parameters: BKTParameters = Field(description="BKT parameters for mastery tracking")


class Curriculum(BaseModel):
    """Complete curriculum structure."""

    version: str = Field(description="Curriculum version")
    description: str = Field(description="Curriculum description")
    episodes: list[int] = Field(description="List of episode numbers covered")
    concepts: list[Concept] = Field(description="All concepts in the curriculum")

    def get_concept(self, concept_id: str) -> Concept | None:
        """Get a concept by ID."""
        for concept in self.concepts:
            if concept.concept_id == concept_id:
                return concept
        return None

    def get_concept_ids(self) -> list[str]:
        """Get all concept IDs."""
        return [c.concept_id for c in self.concepts]

    def build_dag(self) -> dict[str, list[str]]:
        """Build prerequisite DAG from concepts."""
        return {c.concept_id: c.prerequisites for c in self.concepts}
