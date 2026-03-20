#!/usr/bin/env python3
"""Generate filler audio files using ElevenLabs TTS.

This script generates the filler audio files used during thinking pauses.
Run this once to populate the assets/fillers/ directory.

Usage:
    uv run python scripts/generate_fillers.py

Environment variables:
    ELEVENLABS_API_KEY: ElevenLabs API key (required)
    TTS_VOICE_ID: ElevenLabs voice ID (optional, defaults to Rachel)
"""

import asyncio
import os
from pathlib import Path

# Filler phrases by category with variation counts
# Format: (phrase, num_variations)
# Non-lexical fillers like "Mhm" and "Hmm" get multiple variations
FILLERS: dict[str, list[tuple[str, int]]] = {
    "affirmative": [
        ("Mhm", 3),
        ("Right", 2),
        ("Good", 2),
        ("Exactly", 1),
        ("Yes", 2),
    ],
    "thoughtful": [
        ("Hmm", 3),
        ("Okay so", 2),
        ("Let me think", 1),
        ("I see", 1),
        ("Interesting", 1),
    ],
    "neutral": [
        ("Okay", 2),
        ("So", 2),
        ("Well", 2),
        ("Alright", 1),
    ],
}

# Stability settings for variations (lower = more variation in delivery)
STABILITY_SETTINGS = [0.5, 0.4, 0.6]


def get_elevenlabs_client():
    """Initialize ElevenLabs client.

    Returns:
        Configured ElevenLabs client or None if API key not set.
    """
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        print("ELEVENLABS_API_KEY not set, running in dry-run mode")
        return None

    try:
        from elevenlabs import ElevenLabs

        return ElevenLabs(api_key=api_key)
    except ImportError:
        print("elevenlabs package not installed. Install with: pip install elevenlabs")
        return None


def get_voice_id() -> str:
    """Get the voice ID to use for TTS.

    Returns:
        Voice ID from environment or default (Rachel).
    """
    return os.environ.get("TTS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")  # Rachel voice


async def generate_filler(
    client,
    text: str,
    output_path: Path,
    voice_id: str,
    stability: float = 0.5,
) -> bool:
    """Generate a single filler audio file.

    Args:
        client: ElevenLabs client instance.
        text: Text to synthesize.
        output_path: Path to save the MP3 file.
        voice_id: ElevenLabs voice ID.
        stability: Voice stability setting (0.0-1.0).

    Returns:
        True if generation succeeded, False otherwise.
    """
    if client is None:
        print(f"  [dry-run] Would generate: {text} -> {output_path}")
        return False

    try:
        # Generate audio using ElevenLabs
        audio = client.text_to_speech.convert(
            voice_id=voice_id,
            text=text,
            model_id="eleven_monolingual_v1",
            voice_settings={
                "stability": stability,
                "similarity_boost": 0.75,
                "style": 0.0,
                "use_speaker_boost": True,
            },
        )

        # Write audio to file
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as f:
            for chunk in audio:
                f.write(chunk)

        print(f"  Generated: {text} -> {output_path.name}")
        return True

    except Exception as e:
        print(f"  Error generating '{text}': {e}")
        return False


async def generate_category(
    client,
    category: str,
    phrases: list[tuple[str, int]],
    base_path: Path,
    voice_id: str,
) -> int:
    """Generate all fillers for a category.

    Args:
        client: ElevenLabs client instance.
        category: Category name (affirmative, thoughtful, neutral).
        phrases: List of (phrase, num_variations) tuples.
        base_path: Base directory for filler audio.
        voice_id: ElevenLabs voice ID.

    Returns:
        Number of files generated.
    """
    category_path = base_path / category
    category_path.mkdir(parents=True, exist_ok=True)

    generated = 0
    file_index = 0

    for phrase, num_variations in phrases:
        for var in range(num_variations):
            # Create filename: 00_mhm_v0.mp3, 01_mhm_v1.mp3, etc.
            safe_name = phrase.lower().replace(" ", "_")
            if num_variations > 1:
                filename = f"{file_index:02d}_{safe_name}_v{var}.mp3"
            else:
                filename = f"{file_index:02d}_{safe_name}.mp3"

            output_path = category_path / filename

            # Skip if file already exists
            if output_path.exists():
                print(f"  Skipping (exists): {output_path.name}")
                file_index += 1
                continue

            # Use different stability for variations
            stability = STABILITY_SETTINGS[var % len(STABILITY_SETTINGS)]

            if await generate_filler(client, phrase, output_path, voice_id, stability):
                generated += 1

            file_index += 1

            # Small delay to avoid rate limiting
            if client is not None:
                await asyncio.sleep(0.5)

    return generated


async def main() -> None:
    """Generate all filler audio files."""
    base_path = Path("assets/fillers")
    base_path.mkdir(parents=True, exist_ok=True)

    print("Filler Audio Generator")
    print("=" * 50)

    client = get_elevenlabs_client()
    voice_id = get_voice_id()

    if client:
        print(f"Using voice ID: {voice_id}")
    print()

    total_generated = 0

    for category, phrases in FILLERS.items():
        print(f"\n[{category}]")

        # Create .gitkeep to preserve directory structure
        category_path = base_path / category
        category_path.mkdir(parents=True, exist_ok=True)
        (category_path / ".gitkeep").touch()

        generated = await generate_category(
            client, category, phrases, base_path, voice_id
        )
        total_generated += generated

        # Count expected files
        expected = sum(v for _, v in phrases)
        existing = len(list(category_path.glob("*.mp3")))
        print(f"  {existing}/{expected} files present")

    print("\n" + "=" * 50)
    print(f"Generated {total_generated} new files")

    if client is None:
        print("\nTo generate actual audio files:")
        print("  1. Set ELEVENLABS_API_KEY environment variable")
        print("  2. Optionally set TTS_VOICE_ID for a custom voice")
        print("  3. Run this script again")


if __name__ == "__main__":
    asyncio.run(main())
