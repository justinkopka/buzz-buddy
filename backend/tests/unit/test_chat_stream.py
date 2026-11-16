"""chat.stream_answer: which agent events reach the browser, and in what form."""

import os

import pytest

# app.auth reads this at import. No request is authenticated in these tests.
os.environ.setdefault("SUPABASE_URL", "http://127.0.0.1:55321")

from app.agent import ErrorEvent, TextEvent, ToolEndEvent, ToolStartEvent  # noqa: E402
from app.api.routes import chat  # noqa: E402


def _script(monkeypatch, *events):
    async def fake(history):
        for event in events:
            yield event

    monkeypatch.setattr(chat, "run_agent", fake)


async def _body():
    return "".join([chunk async for chunk in chat.stream_answer([])])


async def test_only_text_reaches_the_browser(monkeypatch):
    _script(
        monkeypatch,
        ToolStartEvent(id="t", name="search_whiskey", input={"query": "x"}),
        ToolEndEvent(id="t", name="search_whiskey", is_error=False, raw={"secret": 1}),
        TextEvent("Buy "),
        TextEvent("this."),
    )

    assert await _body() == "Buy this."


@pytest.mark.parametrize(
    ("events", "expected"),
    [
        ([ErrorEvent("Sorry.")], "Sorry."),
        ([TextEvent("Partial"), ErrorEvent("Sorry.")], "Partial\n\nSorry."),
    ],
)
async def test_errors_are_shown_to_the_user(monkeypatch, events, expected):
    _script(monkeypatch, *events)

    assert await _body() == expected
