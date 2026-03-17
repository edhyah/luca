"""Pytest fixtures for the Luca test suite."""

import pytest
from unittest.mock import MagicMock


@pytest.fixture
def mock_settings():
    """Mock settings for testing."""
    settings = MagicMock()
    settings.deepgram_api_key = "test_key"
    settings.elevenlabs_api_key = "test_key"
    settings.anthropic_api_key = "test_key"
    settings.daily_api_key = "test_key"
    settings.database_url = "sqlite+aiosqlite:///:memory:"
    settings.log_level = "DEBUG"
    return settings


@pytest.fixture
def sample_concept():
    """Sample concept for testing."""
    return {
        "id": "test_concept",
        "name": "Test Concept",
        "description": "A test concept",
        "explanation": "This is how we explain it",
        "examples": [
            {"source": "Hello", "target": "Hola"}
        ],
        "expected_patterns": ["hola", "hello"],
        "exercises": [
            {
                "type": "translate",
                "prompt": "How do you say 'Hello'?",
                "expected": ["hola"],
                "hints": ["Think of the greeting"],
            }
        ],
    }


@pytest.fixture
def sample_student_history():
    """Sample student history for testing."""
    return [
        {"concept_id": "greetings", "correct": True, "response_time": 2.5},
        {"concept_id": "greetings", "correct": True, "response_time": 1.8},
        {"concept_id": "pronouns", "correct": False, "response_time": 5.0},
        {"concept_id": "pronouns", "correct": True, "response_time": 3.2},
    ]
