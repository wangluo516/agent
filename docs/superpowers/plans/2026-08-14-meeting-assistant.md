# Smart Meeting Assistant Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a locally runnable, test-first intelligent meeting assistant that creates, queries, and updates meetings through a controlled LangGraph workflow with mock calendar/room APIs and deterministic safety enforcement.

**Architecture:** FastAPI exposes chat and mock integration endpoints. A typed LangGraph workflow uses an injectable natural-language interpreter, immutable conversation state, deterministic policy checks, repository-backed meeting tools, and explicit confirmation before writes. Business data and conversation checkpoints use separate SQLite stores.

**Tech Stack:** Python 3.13, FastAPI, LangGraph, LangChain Core/OpenAI adapter, Pydantic v2, SQLite, httpx, pytest, pytest-cov, Ruff.

## Global Constraints

- Default timezone is exactly `Asia/Shanghai`; tests use an injectable fixed clock.
- Core statement and branch coverage is at least 80%; security and policy branches target at least 95%.
- Production code is written only after a covering test has failed for the expected reason.
- State and domain updates return new values; do not mutate existing models or collections.
- The model interprets language only; identity, authorization, confirmation, and writes are deterministic code.
- No delete, bulk-update, arbitrary SQL, or arbitrary HTTP tool exists.
- Create and update require preview plus explicit confirmation; rejected requests produce zero write side effects.
- The application runs without an API key in `demo` mode and supports an optional real model through environment configuration.

---

### Task 1: Project foundation, domain models, repository, and policies

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `.env.example`
- Create: `app/config.py`, `app/domain/models.py`, `app/domain/errors.py`, `app/domain/policies.py`
- Create: `app/repositories/meetings.py`, `app/repositories/schema.sql`, `app/repositories/seed.py`
- Test: `tests/unit/test_models.py`, `tests/unit/test_policies.py`, `tests/integration/test_repository.py`

**Interfaces:**
- Produces immutable Pydantic models `MeetingDraft`, `MeetingPatch`, `Meeting`, `Actor`, `PendingAction`, `ConversationState`.
- Produces `MeetingRepository` with `list_for_actor`, `find_visible`, `create`, and `update` using parameterized SQLite and optimistic `version` checks.
- Produces pure policies `validate_draft`, `authorize_query`, `authorize_update`, `classify_unsafe_request`, and confirmation hashing.

- [ ] Write model, policy, and repository tests for validation, visibility, organizer-only updates, idempotent create, and optimistic locking.
- [ ] Run focused tests and verify collection/import failures are caused by missing production modules.
- [ ] Implement only the required models, schema, repository, and policies.
- [ ] Run focused tests, refactor while green, and verify the task report records RED and GREEN commands.

### Task 2: Availability, room recommendation, mock APIs, and typed clients

**Files:**
- Create: `app/domain/availability.py`, `app/domain/room_ranking.py`
- Create: `app/integrations/models.py`, `app/integrations/calendar_client.py`, `app/integrations/room_client.py`
- Create: `app/api/mock_integrations.py`, `app/api/dependencies.py`
- Test: `tests/unit/test_availability.py`, `tests/unit/test_room_ranking.py`, `tests/integration/test_mock_integrations.py`

**Interfaces:**
- Consumes `MeetingDraft` and application settings from Task 1.
- Produces `find_common_free_slots(busy_by_user, window_start, window_end, duration_minutes)`.
- Produces deterministic `rank_rooms(rooms, topic, attendee_count, required_features)`.
- Exposes `POST /mock/calendar/freebusy` and `POST /mock/rooms/search`; typed clients validate complete responses and surface controlled integration errors.

- [ ] Write failing interval, ranking, endpoint-contract, and malformed-upstream tests using literal expected values.
- [ ] Run focused tests and verify failures are due to missing behavior.
- [ ] Implement pure algorithms, seed fixtures, endpoints, and typed clients.
- [ ] Run focused tests and refactor without changing behavior.

### Task 3: Intent interpreter and controlled LangGraph workflow

**Files:**
- Create: `app/agent/interpreter.py`, `app/agent/demo_interpreter.py`, `app/agent/llm_interpreter.py`
- Create: `app/agent/state.py`, `app/agent/service.py`, `app/agent/graph.py`, `app/agent/tools.py`
- Test: `tests/unit/test_demo_interpreter.py`, `tests/unit/test_state.py`, `tests/integration/test_agent_workflow.py`

**Interfaces:**
- Consumes repositories, policies, availability and room clients.
- Produces `MeetingCommand` operations `create|query|update|confirm|cancel|unsafe|unknown` and partial `MeetingPatch` values.
- Produces `MeetingAssistant.handle(ChatContext, message) -> AssistantReply` with states `collecting|needs_clarification|needs_confirmation|done|rejected`.
- The graph has bounded nodes for precheck, interpret, reduce/resolve, validate, query integrations, preview, confirm, and execute; it has no unbounded ReAct loop.

- [ ] Write failing tests for incomplete create, multi-turn patching, query, update by context, explicit confirmation, state isolation, unsafe rejection, zero writes, and tool failure.
- [ ] Verify all tests fail for missing workflow behavior.
- [ ] Implement the interpreter interface, deterministic demo interpreter, optional real-model interpreter, immutable state reducer, tools, and graph.
- [ ] Run focused tests; refactor graph nodes below 50 lines where practical while keeping tests green.

### Task 4: FastAPI chat surface and minimal browser UI

**Files:**
- Create: `app/api/chat.py`, `app/main.py`, `app/runtime.py`
- Create: `static/index.html`, `static/app.js`, `static/styles.css`
- Test: `tests/integration/test_chat_api.py`, `tests/e2e/test_user_journeys.py`

**Interfaces:**
- Exposes `POST /api/chat` with `conversation_id`, `message` and demo `actor_id`, returning `reply`, `status`, optional `meeting_draft`, `needs_confirmation`, and `request_id`.
- Exposes `GET /health` and serves the accessible one-page chat UI at `/`.
- E2E API journeys prove create/query/update and unsafe-request zero-side-effect behavior.

- [ ] Write failing route and complete-journey tests before registering endpoints.
- [ ] Run focused tests and verify expected 404/import failures.
- [ ] Implement runtime wiring, routes, exception envelopes, and the dependency-free UI.
- [ ] Run integration/E2E tests and refactor while green.

### Task 5: Reproducibility, documentation, and full verification

**Files:**
- Create: `README.md`, `Dockerfile`
- Modify: `DESIGN.md`, `.env.example`, `pyproject.toml`
- Test: all existing tests

**Interfaces:**
- Produces one-command local startup, deterministic seed/reset instructions, optional real-model configuration, test/coverage commands, and a four-scenario demo script.

- [ ] Install the project in a clean virtual environment and run Ruff plus the complete test suite with branch coverage.
- [ ] Exercise `/health`, the homepage, and all four scripted conversations against a running process.
- [ ] Run dependency/security checks and scan the repository for accidental secrets.
- [ ] Review `DESIGN.md` for the two-page limit, scope consistency, and absence of placeholders.
- [ ] Record exact verification evidence and any remaining limitations in the task report.
