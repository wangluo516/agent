# Task 5 verification report

Date: 2026-08-14 (Asia/Shanghai)

## Deliverables

- Added `README.md`: Windows/POSIX setup, header-based demo identity, deterministic reset, four exact conversation flows, Docker, and verification commands.
- Added `Dockerfile`: Python 3.12 slim image, runtime `uvicorn`, `/data` SQLite volume, and port 8000.
- Added `uvicorn>=0.30,<1` to runtime dependencies; a normal installation can now run the documented server command.
- Corrected `.env.example` to contain only non-secret demo configuration.
- Condensed `DESIGN.md`, corrected its Python floor to `>=3.12`, and documented the actual process-local `(conversation_id, actor_id)` state limitation. It no longer claims `SqliteSaver`/checkpoint persistence or a runtime-selectable real-model path.
- Applied repository-wide Ruff import/format fixes only. The intentional naive-datetime validation inputs have narrow `# noqa: DTZ001` markers; they remain tests of rejection behavior.

## Fresh verification evidence

Clean environment:

```text
.verify-venv: Python 3.12.13
python -m pip install -e '.[dev]' build pip-audit: exit 0
python -m pip check: No broken requirements found.
```

Quality gate:

```text
python -m ruff check .: All checks passed!
python -m ruff format --check .: 45 files already formatted
python -m compileall -q app tests: exit 0
pytest --cov=app --cov-branch --cov-report=term-missing --cov-fail-under=80:
52 passed in 5.23s; total branch coverage 91.77% (minimum 80%).
```

Package build:

```text
python -m build: built meeting_assistant-0.1.0.tar.gz and meeting_assistant-0.1.0-py3-none-any.whl
wheel and sdist each contain app/static/app.js, app/static/index.html, app/static/styles.css
```

Live Uvicorn smoke (a bounded subprocess using `.verify-venv`, port 8765, and a fresh `live-task5.db`):

```text
GET /health: {"ok": true}
GET /: 200; contains aria-live="polite"
update (live-update-clean): done -> needs_confirmation -> done; preview confirmation=True
create (live-create-clean): collecting -> needs_confirmation -> done; preview confirmation=True
busy (live-busy-clean): collecting -> rejected
unsafe (live-unsafe-clean): rejected -> rejected
```

Documentation fix round 1: the README now runs the query/update scenario first. This is required because it selects the one seeded Alice meeting; the create scenario adds a second Alice-visible meeting and would make a later implicit update ambiguous. The exact published order was rechecked against a fresh temporary SQLite runtime:

```text
demo-update: done -> needs_confirmation -> done; preview confirmation=True
demo-create: collecting -> needs_confirmation -> done; preview confirmation=True
demo-busy: collecting -> rejected
demo-unsafe: rejected -> rejected
```

The smoke process was terminated in a `finally` block. Its Uvicorn return code after `terminate()` was `1`, expected for termination rather than an application failure.

Security and hygiene:

```text
git diff --check: exit 0
repository source/config secret scan: no credential-like values found; the only matches are the LLM environment-variable lookup and its use.
```

`pip-audit` 2.10.1 installed successfully, but execution was blocked by a Windows UnicodeDecodeError in `pip_api` while it decodes `pip --version` from this Chinese-path environment (`0xc3` invalid UTF-8 byte). This is a tool/environment encoding limitation, not an advisory result; run `pip-audit` in an ASCII-path CI/virtual environment before release.

## Known limitations

- Conversation drafts, confirmations, and selected-meeting context are process-local; restart loses them. Only committed meetings persist in SQLite.
- The checked-in server always uses `DemoInterpreter`. `LLMInterpreter` has environment-variable support as a library adapter but is not selected by `build_runtime`, so a real model is not currently a supported runtime mode.
- Demo parsing supports the documented Chinese phrases, not broad natural-language coverage. Calendar and room integrations are deterministic in-process mocks.
