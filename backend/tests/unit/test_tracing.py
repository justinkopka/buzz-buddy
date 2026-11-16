"""LangSmith tracing: the agent behaves the same through the wrapped client, and
one request becomes one trace with the Claude and tool calls nested under it.

Tracing runs in "local" mode, which builds the run tree in memory and sends
nothing. Claude is the real SDK against a scripted HTTP transport, as in
test_agent.py, so nothing reaches the network.
"""

import json
import os

import anthropic
import httpx
import pytest
from langsmith import tracing_context
from langsmith.wrappers import wrap_anthropic

# app.auth reads this at import. No request is authenticated in these tests.
os.environ.setdefault("SUPABASE_URL", "http://127.0.0.1:55321")

from app import agent, tools  # noqa: E402
from app.agent import TextEvent, ToolEndEvent, ToolStartEvent  # noqa: E402
from app.api.routes import chat  # noqa: E402
from app.tools import ToolOutcome  # noqa: E402


def _sse(blocks, stop_reason):
    """A streamed Messages response holding text and tool_use blocks."""
    events = [
        (
            "message_start",
            {
                "type": "message_start",
                "message": {
                    "id": "msg_1",
                    "type": "message",
                    "role": "assistant",
                    "model": agent.MODEL,
                    "content": [],
                    "stop_reason": None,
                    "stop_sequence": None,
                    "usage": {"input_tokens": 10, "output_tokens": 0},
                },
            },
        )
    ]
    for index, block in enumerate(blocks):
        if block["type"] == "text":
            start = {"type": "text", "text": ""}
            delta = {"type": "text_delta", "text": block["text"]}
        else:
            start = {**block, "input": {}}
            delta = {"type": "input_json_delta", "partial_json": json.dumps(block["input"])}
        events += [
            ("content_block_start", {"type": "content_block_start", "index": index, "content_block": start}),
            ("content_block_delta", {"type": "content_block_delta", "index": index, "delta": delta}),
            ("content_block_stop", {"type": "content_block_stop", "index": index}),
        ]
    events += [
        (
            "message_delta",
            {
                "type": "message_delta",
                "delta": {"stop_reason": stop_reason, "stop_sequence": None},
                "usage": {"output_tokens": 5},
            },
        ),
        ("message_stop", {"type": "message_stop"}),
    ]
    body = "".join(f"event: {name}\ndata: {json.dumps(data)}\n\n" for name, data in events)
    return httpx.Response(200, headers={"content-type": "text/event-stream"}, text=body)


TOOL_TURN = (
    [
        {"type": "text", "text": "Let me look."},
        {"type": "tool_use", "id": "toolu_1", "name": "resolve_bottle", "input": {"name": "A"}},
    ],
    "tool_use",
)
ANSWER_TURN = ([{"type": "text", "text": "Try A."}], "end_turn")


@pytest.fixture
def wrapped_client(monkeypatch):
    """The scripted transport behind the same wrapper production uses."""
    turns = [TOOL_TURN, ANSWER_TURN]
    requests = []

    def handler(request):
        requests.append(request)
        return _sse(*turns[min(len(requests), len(turns)) - 1])

    client = wrap_anthropic(
        anthropic.AsyncAnthropic(
            api_key="test",
            max_retries=0,
            http_client=anthropic.DefaultAsyncHttpxClient(transport=httpx.MockTransport(handler)),
        )
    )
    monkeypatch.setattr(agent, "get_client", lambda: client)

    async def fake_tool(name, tool_input):
        return ToolOutcome(content="found A", raw={"status": "resolved", "rrf_score": 0.5})

    monkeypatch.setattr(tools, "execute_tool", fake_tool)
    return requests


HISTORY = [{"role": "user", "content": "Is A any good?"}]


async def test_wrapped_client_does_not_change_the_agent(wrapped_client):
    with tracing_context(enabled="local"):
        events = [e async for e in agent.run_agent(HISTORY)]

    assert [type(e) for e in events] == [
        TextEvent,
        ToolStartEvent,
        ToolEndEvent,
        TextEvent,
        TextEvent,
    ]
    assert "".join(e.text for e in events if isinstance(e, TextEvent)) == (
        "Let me look.\n\nTry A."
    )
    assert len(wrapped_client) == 2


async def test_one_request_is_one_trace(wrapped_client):
    finished = []

    with tracing_context(enabled="local"):
        reply = "".join(
            [
                chunk
                async for chunk in chat.stream_answer(
                    HISTORY,
                    langsmith_extra={
                        "metadata": {"user_id": "user-1"},
                        "on_end": finished.append,
                    },
                )
            ]
        )

    assert reply == "Let me look.\n\nTry A."
    (root,) = finished
    assert root.name == "chat"
    assert root.metadata["user_id"] == "user-1"
    assert root.outputs == {"reply": reply}

    children = [(run.run_type, run.name) for run in root.child_runs]
    assert children == [
        ("llm", "ChatAnthropic"),
        ("tool", "resolve_bottle"),
        ("llm", "ChatAnthropic"),
    ]
    assert all(run.trace_id == root.trace_id for run in root.child_runs)

    tool_run = root.child_runs[1]
    assert tool_run.inputs == {"name": "resolve_bottle", "tool_input": {"name": "A"}}
    # The full result, including fields the model never sees.
    assert tool_run.outputs == {
        "is_error": False,
        "result": {"status": "resolved", "rrf_score": 0.5},
    }
