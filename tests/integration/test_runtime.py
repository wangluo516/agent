from pathlib import Path

import pytest

from app.agent.demo_interpreter import DemoInterpreter
from app.config import Settings, load_settings
from app.integrations.calendar_client import CalendarClient
from app.integrations.room_client import RoomClient
from app.runtime import build_interpreter, build_runtime


class StubInterpreter:
    async def interpret(self, message, context):
        raise AssertionError("not called")


def test_settings_reject_invalid_mode() -> None:
    with pytest.raises(ValueError, match="MEETING_ASSISTANT_MODE"):
        Settings(mode="invalid")


def test_load_settings_reads_llm_configuration_without_api_key(monkeypatch) -> None:
    monkeypatch.setenv("MEETING_ASSISTANT_MODE", "llm")
    monkeypatch.setenv("MEETING_ASSISTANT_LLM_MODEL", "small-structured-model")
    monkeypatch.setenv("MEETING_ASSISTANT_LLM_BASE_URL", "https://llm.example/v1")
    monkeypatch.setenv("MEETING_ASSISTANT_LLM_API_KEY", "must-remain-env-only")

    settings = load_settings()

    assert settings.mode == "llm"
    assert settings.llm_model == "small-structured-model"
    assert settings.llm_base_url == "https://llm.example/v1"
    assert "api_key" not in settings.__dataclass_fields__
    assert "must-remain-env-only" not in repr(settings)


def test_interpreter_factory_selects_demo_without_constructing_llm() -> None:
    interpreter = build_interpreter(Settings(mode="demo"))

    assert isinstance(interpreter, DemoInterpreter)


def test_interpreter_factory_selects_llm_with_injected_factory(monkeypatch) -> None:
    sentinel = StubInterpreter()
    captured = {}
    monkeypatch.setenv("MEETING_ASSISTANT_LLM_API_KEY", "secret")

    def factory(*, model, base_url):
        captured.update(model=model, base_url=base_url)
        return sentinel

    interpreter = build_interpreter(
        Settings(mode="llm", llm_model="model-x", llm_base_url="https://llm.example/v1"),
        llm_factory=factory,
    )

    assert interpreter is sentinel
    assert captured == {"model": "model-x", "base_url": "https://llm.example/v1"}


def test_llm_mode_without_api_key_fails_with_controlled_startup_error(monkeypatch) -> None:
    monkeypatch.delenv("MEETING_ASSISTANT_LLM_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="MEETING_ASSISTANT_LLM_API_KEY is required"):
        build_interpreter(Settings(mode="llm"), llm_factory=lambda **kwargs: StubInterpreter())


def test_build_runtime_uses_injected_interpreter(tmp_path: Path) -> None:
    interpreter = StubInterpreter()

    runtime = build_runtime(tmp_path / "runtime.db", interpreter=interpreter)

    assert runtime.assistant._interpreter is interpreter


def test_create_app_passes_loaded_settings_to_runtime_factory(monkeypatch) -> None:
    from app import main

    settings = Settings(mode="demo", database_path=Path("selected.db"))
    sentinel = object()
    captured = {}
    monkeypatch.setattr(main, "load_settings", lambda: settings)

    def fake_build_runtime(*, settings):
        captured["settings"] = settings
        return sentinel

    monkeypatch.setattr(main, "build_runtime", fake_build_runtime)

    application = main.create_app()

    assert application.state.runtime is sentinel
    assert captured == {"settings": settings}


def test_fresh_runtime_seeds_one_visible_demo_meeting_without_duplicates(tmp_path: Path) -> None:
    database_path = tmp_path / "runtime.db"

    first = build_runtime(database_path)
    initial = first.repository.list_for_actor(first.actor("alice"))
    second = build_runtime(database_path)
    repeated = second.repository.list_for_actor(second.actor("alice"))

    assert len(initial) == 1
    assert initial[0].title == "设计评审"
    assert len(repeated) == 1
    assert repeated[0].id == initial[0].id


def test_deleted_demo_seed_is_not_recreated_on_restart(tmp_path: Path) -> None:
    database_path = tmp_path / "runtime.db"
    first = build_runtime(database_path)
    actor = first.actor("alice")
    seeded = first.repository.list_for_actor(actor)[0]

    first.repository.delete("alice", seeded.id, expected_version=seeded.version)
    restarted = build_runtime(database_path)

    assert restarted.repository.list_for_actor(restarted.actor("alice")) == []


@pytest.mark.asyncio
async def test_default_runtime_wires_mock_http_clients(tmp_path: Path) -> None:
    runtime = build_runtime(tmp_path / "runtime.db")

    assert isinstance(runtime.assistant._tools.calendar, CalendarClient)
    assert isinstance(runtime.assistant._tools.rooms, RoomClient)

    await runtime.aclose()
