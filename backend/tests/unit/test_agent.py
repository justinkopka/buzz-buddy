"""The agent loop, with the real Anthropic SDK against a scripted HTTP transport.

Nothing reaches the network, but the SDK's own streaming, parsing, and request
serialization all run. That is the point: a fake client would not notice if
response.content failed to serialize back into the next request.
"""

import json

import anthropic
import httpx
import pytest

from app import agent, tools
from app.agent import ErrorEvent, TextEvent, ToolEndEvent, ToolStartEvent
from app.prompts import SYSTEM_PROMPT
from app.tools import ToolOutcome

HISTORY = [{"role": "user", "content": "What should I buy?"}]


def text(value):
    return {"type": "text", "text": value}


def thinking(signature="sig"):
    return {"type": "thinking", "signature": signature}


def tool_use(id="toolu_1", name="search_whiskey", input=None):
    return {"type": "tool_use", "id": id, "name": name, "input": input or {"query": "x"}}


def _sse_events(blocks, stop_reason):
    yield "message_start", {
        "type": "message_start",
        "message": {
            "id": "msg_1",
            "type": "message",
            "role": "assistant",
            "model": agent.MODEL,
            "content": [],
            "stop_reason": None,
            "stop_sequence": None,
            "usage": {"input_tokens": 1, "output_tokens": 0},
        },
    }
    for index, block in enumerate(blocks):
        if block["type"] == "text":
            start = {"type": "text", "text": ""}
            delta = {"type": "text_delta", "text": block["text"]}
        elif block["type"] == "thinking":
            start = {"type": "thinking", "thinking": "", "signature": ""}
            delta = {"type": "signature_delta", "signature": block["signature"]}
        else:
            start = {**block, "input": {}}
            delta = {"type": "input_json_delta", "partial_json": json.dumps(block["input"])}
        yield "content_block_start", {
            "type": "content_block_start",
            "index": index,
            "content_block": start,
        }
        yield "content_block_delta", {
            "type": "content_block_delta",
            "index": index,
            "delta": delta,
        }
        yield "content_block_stop", {"type": "content_block_stop", "index": index}
    yield "message_delta", {
        "type": "message_delta",
        "delta": {"stop_reason": stop_reason, "stop_sequence": None},
        "usage": {"output_tokens": 1},
    }
    yield "message_stop", {"type": "message_stop"}


def _response(blocks, stop_reason):
    body = "".join(
        f"event: {name}\ndata: {json.dumps(data)}\n\n"
        for name, data in _sse_events(blocks, stop_reason)
    )
    return httpx.Response(200, headers={"content-type": "text/event-stream"}, text=body)


@pytest.fixture
def script(monkeypatch):
    """Queue up responses; returns the request bodies the agent actually sent.

    Each entry is (blocks, stop_reason) or a ready httpx.Response. The last one
    repeats, so an always-calling-tools model needs only one entry.
    """

    def install(*turns):
        requests = []

        def handler(request):
            requests.append(request)
            turn = turns[min(len(requests) - 1, len(turns) - 1)]
            return turn if isinstance(turn, httpx.Response) else _response(*turn)

        client = anthropic.AsyncAnthropic(
            api_key="test",
            max_retries=0,
            http_client=anthropic.DefaultAsyncHttpxClient(
                transport=httpx.MockTransport(handler)
            ),
        )
        monkeypatch.setattr(agent, "get_client", lambda: client)
        return requests

    return install


@pytest.fixture
def executed(monkeypatch):
    """Replaces real tool execution, recording what the agent asked to run."""
    calls = []

    async def fake(name, tool_input):
        calls.append((name, tool_input))
        return ToolOutcome(content=f"result of {name}", raw={"from": name})

    monkeypatch.setattr(tools, "execute_tool", fake)
    return calls


def body(request):
    return json.loads(request.content)


async def run(history=HISTORY):
    return [event async for event in agent.run_agent(history)]


def answer(events):
    return "".join(e.text for e in events if isinstance(e, TextEvent))


# --- request shape ---------------------------------------------------------------


async def test_plain_answer_sends_expected_request(script, executed):
    requests = script(([thinking(), text("Buy Wild Turkey 101.")], "end_turn"))

    events = await run()

    assert answer(events) == "Buy Wild Turkey 101."
    assert executed == []
    sent = body(requests[0])
    assert sent["model"] == "claude-sonnet-5-5"
    assert sent["system"] == SYSTEM_PROMPT
    assert sent["messages"] == HISTORY
    assert sent["tool_choice"] == {"type": "auto"}
    assert sent["output_config"] == {"effort": "medium"}
    assert sent["cache_control"] == {"type": "ephemeral"}
    assert [t["name"] for t in sent["tools"]] == [
        "search_whiskey",
        "resolve_bottle",
        "get_bottle_details",
        "get_related_bottles",
    ]


async def test_caller_history_is_not_mutated(script, executed):
    script(([tool_use()], "tool_use"), ([text("Done.")], "end_turn"))
    history = list(HISTORY)

    await run(history)

    assert history == HISTORY


# --- the loop --------------------------------------------------------------------


async def test_tool_results_go_back_and_the_turn_is_echoed_unchanged(script, executed):
    requests = script(
        ([thinking("keep-me"), tool_use(input={"query": "wheated"})], "tool_use"),
        ([text("Try this.")], "end_turn"),
    )

    events = await run()

    assert executed == [("search_whiskey", {"query": "wheated"})]
    assert answer(events) == "Try this."
    assert [type(e) for e in events] == [ToolStartEvent, ToolEndEvent, TextEvent]

    _, assistant, user = body(requests[1])["messages"]
    assert assistant["role"] == "assistant"
    assert assistant["content"][0]["type"] == "thinking"
    assert assistant["content"][0]["signature"] == "keep-me"
    assert assistant["content"][1]["id"] == "toolu_1"
    assert assistant["content"][1]["input"] == {"query": "wheated"}
    assert user == {
        "role": "user",
        "content": [
            {
                "type": "tool_result",
                "tool_use_id": "toolu_1",
                "content": "result of search_whiskey",
                "is_error": False,
            }
        ],
    }


async def test_parallel_calls_return_in_one_message_in_order(script, executed):
    requests = script(
        (
            [
                tool_use("toolu_a", "resolve_bottle", {"name": "A"}),
                tool_use("toolu_b", "resolve_bottle", {"name": "B"}),
            ],
            "tool_use",
        ),
        ([text("Done.")], "end_turn"),
    )

    await run()

    messages = body(requests[1])["messages"]
    assert len(messages) == 3
    assert [r["tool_use_id"] for r in messages[2]["content"]] == ["toolu_a", "toolu_b"]


async def test_tool_error_is_passed_to_claude_and_the_loop_continues(
    script, monkeypatch
):
    async def failing(name, tool_input):
        return ToolOutcome(content="bad input", is_error=True)

    monkeypatch.setattr(tools, "execute_tool", failing)
    requests = script(([tool_use()], "tool_use"), ([text("Recovered.")], "end_turn"))

    events = await run()

    result = body(requests[1])["messages"][2]["content"][0]
    assert result["is_error"] is True
    assert result["content"] == "bad input"
    assert answer(events) == "Recovered."
    assert next(e for e in events if isinstance(e, ToolEndEvent)).is_error is True


async def test_text_from_separate_turns_does_not_run_together(script, executed):
    script(
        ([text("Let me check."), tool_use()], "tool_use"),
        ([text("Here it is.")], "end_turn"),
    )

    assert answer(await run()) == "Let me check.\n\nHere it is."


# --- limits ----------------------------------------------------------------------


async def test_last_turn_must_answer_and_keeps_the_same_tools(script, executed):
    requests = script(([tool_use()], "tool_use"))

    await run()

    assert len(requests) == agent.MAX_TURNS
    choices = [body(r)["tool_choice"]["type"] for r in requests]
    assert choices == ["auto"] * (agent.MAX_TURNS - 1) + ["none"]
    # Changing the list would invalidate the thinking blocks being replayed.
    assert all(body(r)["tools"] == body(requests[0])["tools"] for r in requests)


# --- stop reasons and failures -----------------------------------------------------


@pytest.mark.parametrize(
    ("stop_reason", "message"),
    [("refusal", agent.REFUSAL_MESSAGE), ("max_tokens", agent.TRUNCATED_MESSAGE)],
)
async def test_cut_off_turns_never_run_their_tools(
    script, executed, stop_reason, message
):
    requests = script(([tool_use()], stop_reason))

    events = await run()

    assert executed == []
    assert len(requests) == 1
    assert events == [ErrorEvent(message)]


async def test_api_error_becomes_a_user_message(script, executed):
    script(httpx.Response(400, json={"type": "error", "error": {"type": "x", "message": "no"}}))

    assert await run() == [ErrorEvent(agent.UNAVAILABLE_MESSAGE)]
