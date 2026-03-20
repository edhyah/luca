"""Custom frames for the Luca pipeline."""

from dataclasses import dataclass, field

from pipecat.frames.frames import DataFrame

from luca.pipeline.pattern_matcher import MatchSignal


@dataclass
class TurnContextFrame(DataFrame):
    """Signals turn context to FillerEngine.

    This frame is pushed by the Orchestrator when transitioning to a new
    curriculum step. It tells the FillerEngine:
    - The difficulty level (affects silence window timing)
    - Available hints for graduated hint delivery
    - The evaluation signal from pattern matching (affects filler pool selection)
    """

    difficulty: int
    hints: list[str] = field(default_factory=list)
    evaluation_signal: MatchSignal | None = None


@dataclass
class HintDeliveredFrame(DataFrame):
    """Signals that a hint was delivered during thinking pause.

    Pushed by FillerEngine when a graduated hint is delivered.
    The Orchestrator uses this to track hints given for context building.
    """

    hint_index: int  # 0-based index of the hint delivered
    total_hints: int  # Total number of hints available for this step
