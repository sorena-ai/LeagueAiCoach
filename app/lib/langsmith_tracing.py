"""LangSmith tracing for the coach and knowledge agents.

LangChain sends a trace automatically when LANGSMITH_TRACING=true. This module
does two extra things the env vars cannot:

- names each run (coach, knowledge, or summary) and attaches filterable tags
- redacts Riot IDs (Name#TAG) from the payload before it is uploaded
"""

import os
import re
from contextlib import contextmanager
from functools import lru_cache
from typing import Any

import langsmith as ls
from langsmith import Client
from langsmith.anonymizer import create_anonymizer

# Riot ID: Name#TAG, or a parenthetical name that may contain spaces,
# e.g. (Hide on bush#KR1). A bare match stays on the last word so a sentence
# like "Coach Player#EUW" does not swallow the word before the name.
_RIOT_ID = re.compile(
    r"(?:"
    r"(?<=\()[\w][\w.' -]{0,16}#[A-Za-z0-9]{2,5}(?=\))"
    r"|"
    r"(?<![\w.'-])[\w][\w.'-]{0,16}#[A-Za-z0-9]{2,5}"
    r")"
)


def redact_player_ids(text: str) -> str:
    """Replace Riot IDs in a string with a placeholder."""
    return _RIOT_ID.sub("<player>", text)


@lru_cache(maxsize=1)
def _tracing_client() -> Client:
    return Client(anonymizer=create_anonymizer(redact_player_ids))


@contextmanager
def langsmith_tracing():
    """Point LangChain's automatic tracer at the redacting client for this call."""
    if os.getenv("LANGSMITH_TRACING", "").lower() != "true":
        yield
        return
    with ls.tracing_context(client=_tracing_client()):
        yield


def trace_config(agent: str, *, tags: list[str] | None = None, **metadata: Any) -> dict:
    """Build the RunnableConfig that names a run and labels it for filtering."""
    run_tags = [agent]
    for tag in tags or []:
        if tag:
            run_tags.append(str(tag))
    fields = {"agent": agent}
    for key, value in metadata.items():
        if value is not None and value != "":
            fields[key] = value
    return {"run_name": agent, "tags": run_tags, "metadata": fields}
