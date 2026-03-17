"""Central state machine orchestrating the tutoring session."""

from enum import Enum

from pipecat.frames.frames import Frame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from luca.utils.logging import get_logger

logger = get_logger("pipeline.orchestrator")


class TutorState(Enum):
    """States of the tutoring state machine."""

    IDLE = "idle"
    PROMPTING = "prompting"
    LISTENING = "listening"
    EVALUATING = "evaluating"
    RESPONDING = "responding"


class Orchestrator(FrameProcessor):
    """Central state machine for managing tutoring flow."""

    def __init__(self) -> None:
        super().__init__()
        self.state = TutorState.IDLE

    def transition_to(self, new_state: TutorState) -> None:
        """Transition to a new state."""
        logger.debug(f"State transition: {self.state} -> {new_state}")
        self.state = new_state

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        """Process frames based on current state."""
        # TODO: Implement state machine logic
        await self.push_frame(frame, direction)
