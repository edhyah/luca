"""Tests for configuration loading."""

import pytest
from luca.utils.config import Settings


class TestSettings:
    """Tests for Settings."""

    def test_default_values(self):
        """Test that settings have sensible defaults."""
        # Create settings without env vars
        settings = Settings(
            _env_file=None,  # Don't load .env file
        )

        assert settings.log_level == "INFO"
        assert settings.tts_provider in ["elevenlabs", "cartesia"]
        assert "postgresql" in settings.database_url

    def test_database_url_format(self):
        """Test database URL is valid format."""
        settings = Settings(_env_file=None)

        # Should be asyncpg format
        assert "asyncpg" in settings.database_url or "aiosqlite" in settings.database_url
