"""Applies to every test.

Tracing is forced off, so a real LANGSMITH_* setup in backend/.env or the shell
can never send test runs to LangSmith. Tests that inspect traces turn it on
locally with tracing_context(enabled="local"), which records but never sends.
"""

import os

os.environ["LANGSMITH_TRACING"] = "false"
