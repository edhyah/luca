"""System prompts and few-shot examples for the tutor agent."""

from luca.tutor.prompts.few_shot_examples import (
    FEW_SHOT_EXAMPLES,
    FewShotExample,
    format_examples_for_prompt,
    get_all_examples_formatted,
    get_examples_for_scenario,
)
from luca.tutor.prompts.system_prompt import TUTOR_SYSTEM_PROMPT, build_system_prompt

__all__ = [
    "TUTOR_SYSTEM_PROMPT",
    "build_system_prompt",
    "FEW_SHOT_EXAMPLES",
    "FewShotExample",
    "format_examples_for_prompt",
    "get_all_examples_formatted",
    "get_examples_for_scenario",
]
