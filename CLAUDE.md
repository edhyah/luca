# Luca Project Guidelines

## Commands

Use `uv` for all Python operations:

```bash
# Run tests
uv run pytest -v

# Run specific test file
uv run pytest tests/test_t2_integration.py -v

# Type checking
uv run mypy src/luca/curriculum/models.py src/luca/student/session_state.py

# Run the application (when applicable)
uv run python -m luca
```

## Project Structure

- `src/luca/` - Main source code
  - `curriculum/` - Curriculum models, loader, and engine
  - `student/` - Student state, BKT model, session tracking
  - `tutor/` - Tutor logic and prompts
  - `pipeline/` - Audio/video pipeline
  - `persistence/` - Database models
  - `utils/` - Shared utilities
- `tests/` - Test files
- `data/` - Curriculum JSON files
