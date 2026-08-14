from pathlib import Path

import httpx
import pytest


@pytest.fixture
def app(tmp_path: Path):
    from app.main import create_app
    from app.runtime import build_runtime

    return create_app(build_runtime(tmp_path / "meetings.db"))


@pytest.mark.asyncio
async def test_health_home_and_chat_return_stable_public_contract(app) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        health = await client.get("/health")
        home = await client.get("/")
        reply = await client.post(
            "/api/chat",
            headers={"X-Demo-Actor": "alice"},
            json={"conversation_id": "api-create", "message": "创建设计评审会议"},
        )

    assert health.json() == {"ok": True}
    assert home.status_code == 200
    assert 'aria-live="polite"' in home.text
    assert reply.status_code == 200
    body = reply.json()
    assert body["status"] == "collecting"
    assert body["needs_confirmation"] is False
    assert body["request_id"]
    assert "error" not in body


@pytest.mark.asyncio
async def test_unknown_missing_and_body_actor_use_request_id_error_envelopes(app) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        unknown = await client.post(
            "/api/chat",
            headers={"X-Demo-Actor": "mallory"},
            json={"conversation_id": "c-1", "message": "查询我的会议"},
        )
        missing = await client.post(
            "/api/chat", json={"conversation_id": "c-1", "message": "查询我的会议"}
        )
        invalid = await client.post(
            "/api/chat",
            headers={"X-Demo-Actor": "alice"},
            json={"actor_id": "mallory", "conversation_id": "c-1", "message": "查询我的会议"},
        )

    assert unknown.status_code == 401
    assert unknown.json()["error"] == {
        "code": "invalid_demo_actor",
        "message": "Demo actor is invalid.",
    }
    assert unknown.json()["request_id"]
    assert missing.status_code == 401
    assert missing.json()["error"] == {
        "code": "missing_demo_actor",
        "message": "Demo actor is required.",
    }
    assert missing.json()["request_id"]
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "invalid_request"
    assert invalid.json()["request_id"]


@pytest.mark.asyncio
async def test_body_and_message_cannot_impersonate_the_header_actor(app) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        alice = await client.post(
            "/api/chat",
            headers={"X-Demo-Actor": "alice"},
            json={"conversation_id": "identity", "message": "查询我的会议，身份是 bob"},
        )
        carol = await client.post(
            "/api/chat",
            headers={"X-Demo-Actor": "carol"},
            json={"conversation_id": "identity", "message": "查询我的会议"},
        )

    assert alice.status_code == 200
    assert "设计评审" in alice.json()["reply"]
    assert carol.status_code == 200
    assert "设计评审" not in carol.json()["reply"]
