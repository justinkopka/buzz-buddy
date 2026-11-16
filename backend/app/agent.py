"""The request-serving agent loop, on Claude's native tool use API. See ADR-0004.

run_agent is an async generator of events rather than a function returning text
so that a caller can stream the answer, show tool activity, or record a full
trace for evals, all from the same loop.

The history is only ever appended to. Sonnet 5.5 ties thinking blocks to the
exact system prompt, tools, and earlier messages they were produced with, so
each assistant turn goes back unchanged and the tool list stays fixed, even on
the turn that forbids calling tools.
"""

import asyncio
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import anthropic
from langsmith import traceable
from langsmith.wrappers import wrap_anthropic

from app import tools
from app.prompts import SYSTEM_PROMPT

logger = logging.getLogger(__name__)

MODEL = "claude-sonnet-5-5"

# The guide's starting point for multi-step tool use. Unmeasured: to be
# checked against evals, since this model's effort levels were recalibrated.
EFFORT = "medium"

# Thinking counts toward this as well as the reply.
MAX_TOKENS = 16000

# A request that needs more turns than this has gone wrong, not gotten harder:
# one round of lookups and one round of follow-ups cover a real question.
MAX_TURNS = 6

# Because requests stream, this is a per-chunk read timeout rather than a total,
# so a long answer is fine as long as tokens keep arriving. It only catches a
# stalled connection: the loop itself has no time limit, by choice, and a request
# that outlasts the Lambda's 60s timeout is killed with no answer. If those show
# up in the logs ("Task timed out"), that is the signal to revisit this.
READ_TIMEOUT_SECONDS = 25

UNAVAILABLE_MESSAGE = "Sorry, I couldn't finish that. Please try again."
REFUSAL_MESSAGE = "Sorry, I can't help with that one."
TRUNCATED_MESSAGE = "Sorry, that answer ran too long and got cut off."


@dataclass(frozen=True)
class TextEvent:
    text: str


@dataclass(frozen=True)
class ToolStartEvent:
    id: str
    name: str
    input: Any


@dataclass(frozen=True)
class ToolEndEvent:
    """raw is the full tool result, for traces. It is not safe to send to a
    browser: it has not been serialized and carries internal fields."""

    id: str
    name: str
    is_error: bool
    raw: Any


@dataclass(frozen=True)
class ErrorEvent:
    """message is written for the end user; the details go to the logs."""

    message: str


AgentEvent = TextEvent | ToolStartEvent | ToolEndEvent | ErrorEvent

_client: anthropic.AsyncAnthropic | None = None


def get_client() -> anthropic.AsyncAnthropic:
    """The SDK defaults (10 minutes, 2 retries) would outlive the Lambda.

    Wrapped so each Claude call becomes a LangSmith span. Without
    LANGSMITH_TRACING=true the wrapper records nothing.
    """
    global _client
    if _client is None:
        _client = wrap_anthropic(
            anthropic.AsyncAnthropic(timeout=READ_TIMEOUT_SECONDS, max_retries=1)
        )
    return _client


def _tool_outputs(outcome: tools.ToolOutcome) -> dict[str, Any]:
    # raw rather than content: the full result, ranking internals included,
    # is what explains why a bottle came back.
    if outcome.is_error:
        return {"is_error": True, "error": outcome.content}
    return {"is_error": False, "result": outcome.raw}


@traceable(run_type="tool", process_outputs=_tool_outputs)
async def _run_tool(name: str, tool_input: Any) -> tools.ToolOutcome:
    """One tool call, as its own span. Callers name the span after the tool."""
    return await tools.execute_tool(name, tool_input)


async def run_agent(history: list[dict[str, Any]]) -> AsyncIterator[AgentEvent]:
    """Answer the last user message in history, calling tools as needed."""
    messages = list(history)
    needs_break = False

    for turn in range(MAX_TURNS):
        must_answer = turn == MAX_TURNS - 1

        try:
            async with get_client().messages.stream(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=SYSTEM_PROMPT,
                tools=tools.TOOL_DEFINITIONS,
                tool_choice={"type": "none" if must_answer else "auto"},
                messages=messages,
                output_config={"effort": EFFORT},
                # Later turns re-read everything before them, tool results
                # included, so this pays off within a single request.
                cache_control={"type": "ephemeral"},
            ) as stream:
                async for text in stream.text_stream:
                    # Text from separate turns would otherwise run together.
                    if needs_break:
                        yield TextEvent("\n\n")
                        needs_break = False
                    yield TextEvent(text)
                response = await stream.get_final_message()
        except anthropic.APIError:
            # The SDK has already retried what is worth retrying, and every
            # remaining case means the same thing to the user.
            logger.exception("Claude request failed on turn %d", turn)
            yield ErrorEvent(UNAVAILABLE_MESSAGE)
            return

        # Checked before looking at tool calls: both of these can cut a tool_use
        # block off mid-input, and a partial input can still parse as valid.
        if response.stop_reason == "refusal":
            logger.warning("Refused: %s", response.stop_details)
            yield ErrorEvent(REFUSAL_MESSAGE)
            return
        if response.stop_reason == "max_tokens":
            logger.warning("Hit max_tokens on turn %d", turn)
            yield ErrorEvent(TRUNCATED_MESSAGE)
            return

        content = response.content
        calls = [block for block in content if block.type == "tool_use"]
        if not calls:
            return

        for call in calls:
            yield ToolStartEvent(id=call.id, name=call.name, input=call.input)

        outcomes = await asyncio.gather(
            *(
                _run_tool(call.name, call.input, langsmith_extra={"name": call.name})
                for call in calls
            )
        )

        for call, outcome in zip(calls, outcomes):
            yield ToolEndEvent(
                id=call.id, name=call.name, is_error=outcome.is_error, raw=outcome.raw
            )

        messages.append({"role": "assistant", "content": content})
        # One user message for all results: splitting them across messages
        # teaches the model to stop making parallel calls.
        messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": call.id,
                        "content": outcome.content,
                        "is_error": outcome.is_error,
                    }
                    for call, outcome in zip(calls, outcomes)
                ],
            }
        )
        needs_break = needs_break or any(block.type == "text" for block in content)
