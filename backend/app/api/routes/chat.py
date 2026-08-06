from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from pydantic import BaseModel
from typing import Literal

import anthropic

from app.auth import CurrentUser, get_current_user

router = APIRouter(tags=["chat"], dependencies=[Depends(get_current_user)])

client = anthropic.AsyncAnthropic()

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
