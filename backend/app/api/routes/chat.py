import logging
import time

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from langsmith import get_current_run_tree, traceable
from langsmith.run_trees import get_cached_client
from langsmith.utils import tracing_is_enabled
from starlette.background import BackgroundTask

from pydantic import BaseModel
from typing import Literal

from app.agent import ErrorEvent, TextEvent, ToolStartEvent, run_agent
from app.auth import CurrentUser, get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"], dependencies=[Depends(get_current_user)])

# Caps how long a request waits on LangSmith. A slow or unreachable LangSmith
# costs at most this much, and the traces are dropped rather than the request.
FLUSH_TIMEOUT_SECONDS = 5

class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str

class ChatRequest(BaseModel):
    messages: list[ChatTurn]


def _reply(chunks: list[str]) -> dict:
    return {"reply": "".join(chunks)}


@traceable(name="chat", run_type="chain", reduce_fn=_reply)
async def stream_answer(messages: list[dict]):
    """Text only for now: the frontend reads the response as raw bytes.

    The root of each request's trace: Claude calls and tool calls nest under it.
    """
    started = False
    tool_names: list[str] = []
    outcome = "ok"
    began = time.monotonic()
    try:
        async for event in run_agent(messages):
            if isinstance(event, TextEvent):
                started = True
                yield event.text
            elif isinstance(event, ToolStartEvent):
                tool_names.append(event.name)
            elif isinstance(event, ErrorEvent):
                outcome = "error"
                yield f"\n\n{event.message}" if started else event.message
    except BaseException:
        outcome = "failed"
        raise
    finally:
        # One line per request, so a CloudWatch entry leads to its trace.
        run = get_current_run_tree()
        logger.info(
            "chat done trace_id=%s outcome=%s tools=%s duration_ms=%d",
            run.trace_id if run else None,
            outcome,
            ",".join(tool_names) or "-",
            (time.monotonic() - began) * 1000,
        )


def _flush_traces() -> None:
    """Send queued traces before Lambda freezes the process after the response.

    Runs as a background task, after the body has gone out. Locally nothing
    freezes, so this only shortens the wait.
    """
    if tracing_is_enabled():
        get_cached_client().flush(timeout=FLUSH_TIMEOUT_SECONDS)


@router.post("/chat-message")
async def chat_message(request: ChatRequest, user: CurrentUser):
    messages = [{"role": t.role, "content": t.content} for t in request.messages]
    return StreamingResponse(
        stream_answer(messages, langsmith_extra={"metadata": {"user_id": user.id}}),
        media_type="text/event-stream",
        background=BackgroundTask(_flush_traces),
    )
