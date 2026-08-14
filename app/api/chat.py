from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import Field

from app.agent.service import AssistantReply, ChatContext
from app.domain.models import Actor, ImmutableModel, MeetingDraft, MeetingPatch
from app.runtime import Runtime

router = APIRouter(prefix="/api", tags=["chat"])


class ChatRequest(ImmutableModel):
    conversation_id: str = Field(min_length=1, max_length=200)
    message: str = Field(min_length=1, max_length=4_000)


class ChatResponse(ImmutableModel):
    reply: str
    status: str
    meeting_draft: MeetingDraft | MeetingPatch | None = None
    needs_confirmation: bool = False
    request_id: str


def request_id(request: Request) -> str:
    return getattr(request.state, "request_id", str(uuid4()))


def _runtime(request: Request) -> Runtime:
    return request.app.state.runtime


def demo_actor(
    request: Request,
    x_demo_actor: Annotated[str | None, Header()] = None,
) -> Actor:
    """Resolve demo identity at the HTTP boundary; replace with auth in production."""
    if x_demo_actor is None:
        raise HTTPException(
            status_code=401,
            detail={"code": "missing_demo_actor", "message": "Demo actor is required."},
        )
    actor = _runtime(request).actor(x_demo_actor)
    if actor is None:
        raise HTTPException(
            status_code=401,
            detail={"code": "invalid_demo_actor", "message": "Demo actor is invalid."},
        )
    return actor


@router.post("/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    request: Request,
    actor: Annotated[Actor, Depends(demo_actor)],
) -> AssistantReply:
    return await _runtime(request).assistant.handle(
        ChatContext(
            actor=actor, conversation_id=payload.conversation_id, request_id=request_id(request)
        ),
        payload.message,
    )
