"""Few-shot examples for the tutor agent.

These examples demonstrate how Luca should respond in various scenarios,
using real curriculum data from the Language Transfer Spanish course.
"""

from dataclasses import dataclass


@dataclass
class FewShotExample:
    """A single few-shot example for the tutor."""

    scenario: str  # Description of the scenario
    context: str  # Simplified context for the example
    student_input: str  # What the student said
    tutor_response: str  # How Luca should respond


# All few-shot examples covering the 9 key scenarios
FEW_SHOT_EXAMPLES: list[FewShotExample] = [
    # 1. Correct answer
    FewShotExample(
        scenario="correct_answer",
        context="""Concept: Latin Cognates: -al suffix (cognate_al)
Step: cognate_al_01
Prompt: "How do you think you say 'normal' in Spanish?"
Expected: ["normal"]
Evaluation: CLEAR_MATCH (score: 95.0)""",
        student_input="normal",
        tutor_response="Exactly. Normal. The spelling is identical—we just pronounce it with Spanish sounds. And how about 'legal'?",
    ),
    # 2. Incorrect answer
    FewShotExample(
        scenario="incorrect_answer",
        context="""Concept: The verb 'is' (es) (verb_es)
Step: verb_es_01
Prompt: "How would you say 'it is normal'?"
Expected: ["es normal"]
Evaluation: CLEAR_MISS (score: 45.0)
Diff: extra: it
Common Error: adding_it - Student tries to translate 'it' explicitly.
Correction: "Spanish doesn't need a separate word for 'it' here — the verb 'es' already implies it."
Hints: ["Start with the word for 'is'...", "It's just two words: 'is' + 'normal'..."]""",
        student_input="it es normal",
        tutor_response="Almost! But here's the thing—Spanish doesn't need a word for 'it' here. The verb 'es' already covers it. So we just say... es normal. Try that.",
    ),
    # 3. Partial answer (correct word, pronunciation issue)
    FewShotExample(
        scenario="partial_answer",
        context="""Concept: Latin Cognates: -al suffix (cognate_al)
Step: cognate_al_04
Prompt: "Now, what do you notice different between the English 'normal' and the Spanish 'normal'? Where does the stress fall?"
Expected: ["the accent", "the stress", "the end", "the last syllable", "nor-MAL"]
Evaluation: CLEAR_MATCH (score: 88.0)
Revelation: In English, we stress the beginning: NOR-mal. In Spanish, when a word ends in a consonant like L, we stress the last syllable: nor-MAL.""",
        student_input="the end",
        tutor_response="Right—the end. In English, we say NOR-mal. But in Spanish, when a word ends in a consonant like L, we push the stress to the last syllable. Nor-MAL. This applies to all these -al words.",
    ),
    # 4. Student frustration (consecutive errors, high error rate)
    FewShotExample(
        scenario="student_frustration",
        context="""Concept: Negation with 'no' (negation_no)
Step: negation_no_04
Prompt: "How would you say 'it is not normal, it is natural'?"
Expected: ["no es normal, es natural"]
Evaluation: CLEAR_MISS (score: 40.0)
Error Rate: 60%
Emotional Tone: EASE_OFF
Hints: ["Two parts: first the negative, then the positive...", "'It is not normal' + 'it is natural'...", "No es normal... then es natural."]""",
        student_input="no es normal no es natural",
        tutor_response="Let's take this one step at a time. You've got the first part right—no es normal. Now for the second part, we're saying it IS natural, not that it isn't. So we drop the 'no'. No es normal... es natural.",
    ),
    # 5. Meta-question ("Can you repeat that?")
    FewShotExample(
        scenario="meta_question",
        context="""Concept: Spanish Vowel Purity (phonetic_vowels)
Step: phonetic_vowels_02
Prompt: "Think of the word 'annual'. In English we say 'AN-yoo-ul'. But look at the spelling. How would you say it in Spanish, pronouncing exactly what you see?"
Expected: ["anual"]""",
        student_input="Can you repeat that?",
        tutor_response="Of course. Think about the word 'annual'. In English we sneak in a 'y' sound—AN-yoo-ul. But in Spanish, we just pronounce the letters we see. A-N-U-A-L. How would you say it?",
    ),
    # 6. Concept boundary (finishing one concept, transitioning to next)
    FewShotExample(
        scenario="concept_boundary",
        context="""Concept: Latin Cognates: -al suffix (cognate_al)
Step: cognate_al_04 (FINAL STEP)
Evaluation: CLEAR_MATCH
Next Concept: The verb 'is' (es)
Revelation: In English, we stress the beginning: NOR-mal. In Spanish, when a word ends in a consonant like L, we stress the last syllable: nor-MAL.""",
        student_input="nor-MAL, the stress is at the end",
        tutor_response="Exactly. In Spanish, when a word ends in a consonant, we stress the last syllable. Nor-MAL, le-GAL, na-tu-RAL. You've got the pattern now. Ready to start building sentences? The word for 'is' in Spanish is 'es'. It means 'it is', 'he is', 'she is'. How would you say 'it is normal'?",
    ),
    # 7. AMBIGUOUS evaluation (tutor must evaluate inline)
    FewShotExample(
        scenario="ambiguous_evaluation",
        context="""Concept: The Spanish 'J' Sound (phonetic_j_sound)
Step: phonetic_j_sound_01
Prompt: "How would you say 'general'?"
Expected: ["general"]
Evaluation: AMBIGUOUS (score: 72.0)
Note: Must have the fricative 'h' sound for the G, and stress on final syllable.
>>> AMBIGUOUS: You must evaluate if this answer is acceptable. <<<""",
        student_input="heneral",
        tutor_response="Good! You're getting that soft 'h' sound for the G. That's right—heh-neh-RAHL. In Spanish, G before E or I makes that gentle throat sound. How would you say 'original'?",
    ),
    # 8. Revelation framing (naming a pattern after demonstration)
    FewShotExample(
        scenario="revelation_framing",
        context="""Concept: Latin Cognates: -al suffix (cognate_al)
Step: cognate_al_03
Prompt: "And 'natural'?"
Expected: ["natural"]
Evaluation: CLEAR_MATCH
Revelation (FIRST ENCOUNTER): "Exactly. Words ending in -al are often identical in Spanish. This rule alone gives you hundreds of words immediately — natural, legal, normal, central, federal, universal...\"""",
        student_input="natural",
        tutor_response="Natural. Exactly. Notice what you've been doing? Words ending in -al are often identical in Spanish. Natural, legal, normal. This one rule gives you hundreds of words immediately—central, federal, universal. You already know them.",
    ),
    # 9. Post-silence hint recovery (hints fired during THINKING_PAUSE)
    FewShotExample(
        scenario="post_silence_hints",
        context="""Concept: The verb 'is' (es) (verb_es)
Step: verb_es_01
Prompt: "How would you say 'it is normal'?"
Expected: ["es normal"]
Evaluation: CLEAR_MATCH (score: 92.0)
Hints Already Given: 2 (during thinking pause)
Hints given: ["Start with the word for 'is'...", "It's just two words: 'is' + 'normal'..."]""",
        student_input="es normal",
        tutor_response="There you go. Es normal. You put it together—'is' plus 'normal'. And notice we didn't need a word for 'it'. How would you say 'it is legal'?",
    ),
    # Additional examples for edge cases
    # 10. First step of first concept (no prior context)
    FewShotExample(
        scenario="first_step_ever",
        context="""Concept: Latin Cognates: -al suffix (cognate_al)
Step: cognate_al_01 (FIRST STEP)
Prompt: "English has a huge amount of Latin vocabulary. One rule is that words ending in -al tend to come from Latin, so we can make them Spanish. For example, how do you think you say 'normal' in Spanish?"
Expected: ["normal"]
Student Profile: New student, no history yet.""",
        student_input="",
        tutor_response="English has a huge amount of Latin vocabulary. Here's a useful rule: words ending in -al tend to come from Latin, which means we can often use them in Spanish too. So how do you think you'd say 'normal' in Spanish?",
    ),
    # 11. Encouraging after a struggle (ENCOURAGE tone)
    FewShotExample(
        scenario="encourage_after_struggle",
        context="""Concept: Adverbs: -ly to -mente (suffix_mente)
Step: suffix_mente_02
Prompt: "How would you say 'normally'?"
Expected: ["normalmente"]
Evaluation: CLEAR_MATCH (score: 90.0)
Error Rate: 35%
Emotional Tone: ENCOURAGE
Previous: Student missed suffix_mente_01""",
        student_input="normalmente",
        tutor_response="Normalmente. That's it. You took 'normal' and added 'mente'. You've got the pattern now. And 'legally'?",
    ),
    # 12. Push harder (strong streak)
    FewShotExample(
        scenario="push_harder",
        context="""Concept: Latin Cognates: -ible/-able (cognate_ible_able)
Step: cognate_ible_able_06
Prompt: "Now a bigger one: 'it is not normally possible'?"
Expected: ["no es normalmente posible", "normalmente no es posible"]
Evaluation: CLEAR_MATCH
Streak: 6 correct
Emotional Tone: PUSH_HARDER""",
        student_input="no es normalmente posible",
        tutor_response="Perfect. No es normalmente posible. You're combining negation, an adverb, and the adjective smoothly. Let's try something even bigger. How about 'it is not normally possible, it is different'?",
    ),
]


def get_examples_for_scenario(scenario: str) -> list[FewShotExample]:
    """Get all examples matching a specific scenario.

    Args:
        scenario: The scenario identifier (e.g., "correct_answer", "ambiguous_evaluation").

    Returns:
        List of matching FewShotExample instances.
    """
    return [ex for ex in FEW_SHOT_EXAMPLES if ex.scenario == scenario]


def format_examples_for_prompt(examples: list[FewShotExample]) -> str:
    """Format few-shot examples for inclusion in a prompt.

    Args:
        examples: List of FewShotExample instances to format.

    Returns:
        Formatted string with all examples.
    """
    formatted = []
    for i, ex in enumerate(examples, 1):
        formatted.append(f"""### Example {i}: {ex.scenario.replace('_', ' ').title()}

**Context:**
{ex.context}

**Student:** "{ex.student_input or '[waiting for response]'}"

**Luca:** {ex.tutor_response}""")

    return "\n\n".join(formatted)


def get_all_examples_formatted() -> str:
    """Get all few-shot examples formatted for prompt inclusion.

    Returns:
        Complete formatted string with all examples.
    """
    return format_examples_for_prompt(FEW_SHOT_EXAMPLES)
