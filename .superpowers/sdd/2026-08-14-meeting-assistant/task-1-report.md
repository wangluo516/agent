# Task 1 Report: project foundation, domain models, repository, and policies

## Files delivered

- `pyproject.toml`, `.gitignore`, `.env.example`
- `app/config.py`
- `app/domain/models.py`, `app/domain/errors.py`, `app/domain/policies.py`
- `app/repositories/meetings.py`, `app/repositories/schema.sql`, `app/repositories/seed.py`
- `tests/unit/test_models.py`, `tests/unit/test_policies.py`, `tests/integration/test_repository.py`

## TDD evidence

### RED

Command: `pytest tests/unit/test_models.py tests/unit/test_policies.py tests/integration/test_repository.py -q`

Result: expected initial RED execution could not start because `pytest` was not installed and the configured Python 3.13 launcher referenced a missing executable. The tests were written first, before any production modules existed. The usable bundled Python 3.12.13 runtime was then used to create `.venv` and install project/test dependencies. (The first `.[dev]` install also revealed that the configured package index did not offer Ruff.)

### GREEN

Command: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_models.py tests/unit/test_policies.py tests/integration/test_repository.py -q`

Result: `12 passed in 1.51s`.

Verification command: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_models.py tests/unit/test_policies.py tests/integration/test_repository.py --cov=app --cov-branch --cov-report=term-missing -q`

Result: `12 passed`; aggregate application branch coverage was `80%`.

## Tests

- Models: timezone-aware, positive intervals; immutable actor; immutable conversation-state merging.
- Policies: draft attendee validation; meeting visibility; organizer-only updates; unsafe deletion/SQL classification; parameter-sensitive confirmation hashes.
- Repository: idempotent create; actor-limited lookup; optimistic locking.

## Self-review

- All SQLite operations use bound parameters.
- Repository reads filter attendee visibility using parsed JSON after a parameterized candidate query, preventing substring-only authorization decisions.
- Writes are scoped by organizer, meeting id, and expected version.
- Models forbid unknown fields and are frozen.
- No delete, bulk update, arbitrary SQL, or arbitrary HTTP capability was introduced.

## Concerns

- The project's stated Python 3.13 runtime was unavailable in this environment. `pyproject.toml` therefore sets `requires-python = ">=3.12"` to support the available Python 3.12.13 runtime; the design document can be reconciled in Task 5.
- Ruff could not be installed from the available package index, so Ruff verification was not performed.

## Commit

`e08dec5a380a604e0a0230c2556bbda4fba94833` (`feat: add meeting domain foundation`)

## Fix round 1/5

### Regression RED

Command: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_models.py tests/unit/test_policies.py tests/integration/test_repository.py -q`

Result: `5 failed, 12 passed in 0.55s`. The failures proved that UTC values were not normalized to Asia/Shanghai, generic SQL and HTTP-style requests bypassed unsafe classification, idempotency keys leaked the first organizer's meeting to a different organizer, and empty patches incremented meeting versions.

### Changes

- Normalized accepted aware timestamps to fixed `Asia/Shanghai` (+08:00) values without relying on unavailable system `tzdata`.
- Scoped SQLite idempotency uniqueness and lookup to `(organizer_id, idempotency_key)`.
- Rejected no-op `MeetingPatch()` updates before opening a write transaction.
- Classified SQL verbs and explicit HTTP-method-plus-URL instructions as unsupported.
- Added focused regression tests for every finding.

### GREEN

Command: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_models.py tests/unit/test_policies.py tests/integration/test_repository.py --cov=app --cov-branch --cov-report=term-missing -q`

Result: `17 passed in 0.82s`; aggregate application branch coverage `81%`.

### Fix-round concerns

- The fixed +08:00 Shanghai timezone accurately represents the product's declared default but does not carry an IANA zone object; this avoids a runtime `tzdata` dependency in the supplied Windows Python runtime.
- Commit SHA: `c6d0a88fbb8f3e8d5e2b3837ebd639960a311de1` (`fix: harden meeting foundation policies`).

## Fix round 2/5

### Regression RED

Command: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_models.py tests/unit/test_policies.py -q`

Result: `4 failed, 11 passed in 0.35s`. The failures proved that the timezone was a fixed offset rather than `ZoneInfo("Asia/Shanghai")`, explicit `None` datetime patch fields raised `AttributeError`, and ordinary English create/update requests were over-classified as SQL.

### Changes

- Added runtime dependency `tzdata>=2024.1` and use `ZoneInfo("Asia/Shanghai")` for normalizing aware datetime values.
- Preserve explicit `None` for optional `MeetingPatch` datetime fields.
- Narrowed SQL safety classification to SQL-shaped constructs, while retaining detection of `SELECT … FROM`, DDL/DML syntax, and `UNION SELECT`.
- Added safe meeting-command and real IANA-zone regression tests.

### GREEN

Command: `.\.venv\Scripts\python.exe -m pytest tests/unit/test_models.py tests/unit/test_policies.py tests/integration/test_repository.py --cov=app --cov-branch --cov-report=term-missing -q`

Result: `20 passed in 0.77s`; aggregate application branch coverage `82%`.

### Fix-round concerns

- Commit SHA: `6a6e88dacd5502a9764d6e3b4b8ba2fdec795095` (`fix: preserve meeting command safety`).
