# LLM Runtime Hardening Report

## Outcome

- Added fail-fast `demo | llm` mode validation.
- Added model and optional base URL settings while keeping the API key environment-only.
- Added a runtime interpreter factory with injectable LLM factory/interpreter seams.
- Wired `app.main.create_app()` through the complete `Settings` object.
- Preserved the deterministic, key-free demo and the existing fixed LangGraph workflow.
- Documented real LLM startup and small structured-output model selection.

## TDD evidence

- RED: `pytest tests/integration/test_runtime.py -q` failed during collection because `build_interpreter` did not exist.
- GREEN: focused runtime suite passed: `8 passed`.
- Full suite: `62 passed`.

## Verification

- `python -m ruff check .`: passed.
- `python -m ruff format --check .`: 46 files already formatted.
- `python -m compileall -q app tests`: passed.
- `pytest --cov=app --cov-branch --cov-report=term-missing --cov-fail-under=80`: 62 passed, 92.48% total coverage.
- `git diff --check`: passed (only Git line-ending notices on Windows).
- Secret scan found only explicit test placeholders and documented environment-variable names; no API key is stored in `Settings` or `.env.example`.

## Concerns

- Real provider connectivity was intentionally not exercised because tests must not construct or call a live LLM. The injected factory test proves LLM selection and propagation of model/base URL.
- Existing actor authentication and calendar/room integrations remain demo implementations; LLM mode changes only structured command extraction.
