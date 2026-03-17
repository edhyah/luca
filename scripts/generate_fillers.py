#!/usr/bin/env python3
"""Generate filler audio files using TTS.

This script generates the filler audio files used during thinking pauses.
Run this once to populate the assets/fillers/ directory.
"""

import asyncio
import os
from pathlib import Path

# Filler phrases by category
FILLERS = {
    "affirmative": [
        "Mhm",
        "Yes",
        "Right",
        "Good",
        "Exactly",
    ],
    "thoughtful": [
        "Hmm",
        "Let me think",
        "Interesting",
        "I see",
    ],
    "neutral": [
        "Okay",
        "Alright",
        "So",
        "Well",
    ],
}


async def generate_filler(text: str, output_path: Path) -> None:
    """Generate a single filler audio file."""
    # TODO: Implement TTS generation
    # This would use ElevenLabs or Cartesia API
    print(f"Would generate: {text} -> {output_path}")


async def main() -> None:
    """Generate all filler audio files."""
    base_path = Path("assets/fillers")

    for category, phrases in FILLERS.items():
        category_path = base_path / category
        category_path.mkdir(parents=True, exist_ok=True)

        # Create .gitkeep to preserve directory structure
        (category_path / ".gitkeep").touch()

        for i, phrase in enumerate(phrases):
            output_path = category_path / f"{i:02d}_{phrase.lower().replace(' ', '_')}.mp3"
            await generate_filler(phrase, output_path)

    print(f"Filler directories created in {base_path}")
    print("Run with TTS API keys configured to generate actual audio files.")


if __name__ == "__main__":
    asyncio.run(main())
