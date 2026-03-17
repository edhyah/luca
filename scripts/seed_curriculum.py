#!/usr/bin/env python3
"""Seed the curriculum with initial concepts.

This script creates a basic set of curriculum concepts for Spanish learning,
following the Language Transfer methodology.
"""

import json
from pathlib import Path

# Initial concepts for Spanish (beginner)
CONCEPTS = [
    {
        "id": "greetings",
        "name": "Basic Greetings",
        "description": "Common greetings and farewells",
        "explanation": "Spanish greetings are straightforward. 'Hola' is universal and easy to remember.",
        "cognates": [],
        "examples": [
            {"source": "Hello", "target": "Hola"},
            {"source": "Good morning", "target": "Buenos dias"},
            {"source": "Goodbye", "target": "Adios"},
        ],
        "exercises": [
            {
                "type": "translate",
                "prompt": "How would you say 'Hello' in Spanish?",
                "expected": ["hola"],
                "hints": ["This is the most common greeting"],
            }
        ],
        "expected_patterns": ["hola", "buenos dias", "adios"],
        "common_errors": [],
        "tags": ["beginner", "greetings"],
        "estimated_time_minutes": 3,
    },
    {
        "id": "pronouns",
        "name": "Subject Pronouns",
        "description": "I, you, he, she, we, they",
        "explanation": "Spanish often drops the subject pronoun because the verb ending tells you who's doing the action.",
        "cognates": [],
        "examples": [
            {"source": "I", "target": "Yo"},
            {"source": "You (informal)", "target": "Tu"},
            {"source": "He/She", "target": "El/Ella"},
        ],
        "exercises": [
            {
                "type": "translate",
                "prompt": "What's the Spanish word for 'I'?",
                "expected": ["yo"],
                "hints": ["This is the first-person singular pronoun"],
            }
        ],
        "expected_patterns": ["yo", "tu", "el", "ella", "nosotros"],
        "common_errors": [],
        "tags": ["beginner", "grammar"],
        "estimated_time_minutes": 5,
    },
]


def main() -> None:
    """Create curriculum concept files."""
    concepts_path = Path("curriculum/concepts")
    concepts_path.mkdir(parents=True, exist_ok=True)

    for concept in CONCEPTS:
        file_path = concepts_path / f"{concept['id']}.json"
        with open(file_path, "w") as f:
            json.dump(concept, f, indent=2)
        print(f"Created: {file_path}")

    print(f"\nCreated {len(CONCEPTS)} concept files in {concepts_path}")


if __name__ == "__main__":
    main()
