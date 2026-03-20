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
