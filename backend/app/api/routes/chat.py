from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from pydantic import BaseModel
from typing import Literal

import anthropic

from app.auth import CurrentUser, get_current_user

router = APIRouter(tags=["chat"], dependencies=[Depends(get_current_user)])

# Sized against the Lambda's 60s timeout. The SDK defaults are 10 minutes with
# 2 retries, and timeouts are themselves retried -- a worst case of 30 minutes,
# so the Lambda would be killed long before the client gave up and the caller
# would get a truncated connection instead of an error.
#
# 25s x (1 retry + 1) = 50s worst case, leaving headroom inside the 60s budget.
# Because this endpoint streams, 25s is a per-chunk read timeout rather than a
# total, so a long answer is fine as long as tokens keep arriving.
client = anthropic.AsyncAnthropic(timeout=25.0, max_retries=1)

class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str

class ChatRequest(BaseModel):
    messages: list[ChatTurn]

async def stream_answer(messages: list[dict]):
    async with client.messages.stream(
            model="claude-sonnet-5",
            max_tokens=5000,
            messages=messages,
        ) as stream:
            async for text in stream.text_stream:
                yield text


@router.post("/chat-message")
async def chat_message(request: ChatRequest, user: CurrentUser):
    messages = [{"role": t.role, "content": t.content} for t in request.messages]
    return StreamingResponse(
        stream_answer(messages),
        media_type="text/event-stream",
    )
