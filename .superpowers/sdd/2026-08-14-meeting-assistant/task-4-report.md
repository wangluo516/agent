# Task 4 Report: Chat API, Runtime, and Browser UI

## Status

Implemented and committed as `cf59458` (`feat: add meeting chat API and demo UI`).

## RED evidence

The shell did not expose `pytest`, so the bundled virtualenv runner was used.

True route/journey RED command:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/integration/test_chat_api.py tests/e2e/test_user_journeys.py -q
```

Result: 5 expected collection errors, each `ModuleNotFoundError: No module named 'app.main'`. The API/UI/runtime did not yet exist.

After the first minimal surface, the same command was RED because `langgraph` had not yet been installed in the virtualenv. Installing the project exposed a packaging issue: a top-level `static` directory caused setuptools to discover both `app` and `static`. The package configuration was explicitly restricted to `app*`, then static assets were moved under `app/static` and included as package data.

Behavior refinement RED: the creation journey selected `room-lotus` rather than the expected design-labelled room. Adding the Chinese `设计` topic to Orchid made the public demo fixture align with its documented scenario.

## GREEN evidence

Focused API/E2E verification:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/integration/test_chat_api.py tests/e2e/test_user_journeys.py -q
```

Result: `6 passed in 1.26s`.

Full branch-coverage regression:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -q --cov=app --cov-branch --cov-report=term-missing
```

Result: `50 passed in 4.79s`; total coverage `91%`.

Additional checks:

- Scoped Ruff passed for Task 4 files and tests.
- `git diff --check` passed.
- A no-dependency wheel build passed and its archive includes `app/static/app.js`, `app/static/index.html`, and `app/static/styles.css`.

## Files

- `app/api/chat.py`
- `app/main.py`
- `app/runtime.py`
- `app/static/index.html`
- `app/static/app.js`
- `app/static/styles.css`
- `tests/integration/test_chat_api.py`
- `tests/e2e/test_user_journeys.py`
- `pyproject.toml`
- `.gitignore`

## Requirements and self-review

- `POST /api/chat` validates bounded `actor_id`, `conversation_id`, and message inputs. Actor lookup is server-owned and restricted to configured demo actors; the interpreter cannot choose identity.
- All normal and error responses contain a request ID. Validation, unknown actors, and unexpected failures use the same `{error: {code, message}, request_id}` envelope; the request ID is also returned in `X-Request-ID`.
- Runtime uses a SQLite `MeetingRepository`, real Task 3 `MeetingAssistant`/LangGraph, deterministic in-process availability and room ports, configured demo actors, rooms, and a busy Carol interval. No network or model key is needed in demo mode.
- API journeys verify health and UI, clarification, free-busy/room preview, explicit confirmation, query, contextual "刚才那个会" update to 3pm, unsafe delete and SQL/prompt-injection rejection with zero writes, and a busy-attendee no-write path.
- The responsive, dependency-free UI uses a labelled form, visible keyboard focus, live announcements, and text-only rendering (no HTML interpolation).
- Wheel packaging is reproducible: static assets live in `app/static` and package-data explicitly includes them.

## Concerns

- Conversation state remains intentionally in process; a durable checkpoint store is not part of the existing Task 3 public interface.
- The UI's actor is the explicitly documented demo actor `alice`; production authentication is out of scope.
- Repository-wide Ruff still reports pre-existing issues in Task 1/2 files. Task 4-owned files are clean.

## Fix round 1: boundary-owned demo identity and runtime seeds

### RED evidence

```powershell
& '.\.venv\Scripts\python.exe' -m pytest tests/integration/test_chat_api.py tests/integration/test_runtime.py tests/e2e/test_user_journeys.py -q
```

Result: 8 failures. Header-based calls returned `422` because body `actor_id` was still required, and a fresh runtime had zero seeded meetings.

### GREEN evidence

The same focused command passed: `8 passed in 1.42s`.

Final regression command:

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -q --cov=app --cov-branch --cov-report=term-missing
```

Result: `52 passed in 4.97s`; total coverage `92%`. Scoped Ruff and `git diff --check` passed.

### Changes and review

- `ChatRequest` no longer accepts `actor_id`; frozen Pydantic request models reject it as an extra field.
- `X-Demo-Actor` is resolved via a typed FastAPI dependency at the HTTP boundary. Missing and unknown identities return the same controlled `401` class; the dependency documents replacement with production authentication.
- The browser sends fixed demo header `alice`; its JSON body has no identity field. Tests prove body and model text cannot change the header-resolved actor.
- `build_runtime` now uses existing idempotent seed support with a deterministic, visible Alice meeting. Tests cover fresh initialization and repeat initialization without duplication.
