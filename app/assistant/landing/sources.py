"""Turn tool-call file paths into GitHub links for the landing response."""

from typing import Literal
from urllib.parse import quote, urlencode

from langchain_core.messages import ToolMessage
from pydantic import BaseModel

from app.config import settings

# U.GG files are regenerated every patch. A hand edit there is overwritten,
# so those files get an issue link and no edit link.
_UGG_PREFIXES = ("champion-builds/", "champion-counters/")

# Stay under 8 KB so the prefilled issue URL survives browsers and GitHub.
_MAX_URL_CHARS = 8192


class SourceLink(BaseModel):
    """One file an answer used, as the landing page should render it."""

    path: str
    url: str
    origin: Literal["ugg", "curated"]
    edit_url: str | None = None


def collect_source_paths(messages: list) -> list[str]:
    """File paths from this turn's tool results, de-duplicated, first seen first.

    History messages are plain dicts, so every ``ToolMessage`` in the agent
    result belongs to the current turn.
    """
    seen: set[str] = set()
    ordered: list[str] = []
    for message in messages:
        if not isinstance(message, ToolMessage):
            continue
        artifact = message.artifact
        if not isinstance(artifact, list):
            continue
        for path in artifact:
            if isinstance(path, str) and path not in seen:
                seen.add(path)
                ordered.append(path)
    return ordered


def _file_url(kind: str, path: str) -> str:
    base = settings.data_repo_url.rstrip("/")
    branch = quote(settings.data_repo_branch, safe="")
    relative = quote(path, safe="/")
    return f"{base}/{kind}/{branch}/{relative}"


def source_links(paths: list[str]) -> list[SourceLink]:
    """Blob links for every path. Curated files also get an edit link."""
    links: list[SourceLink] = []
    for path in paths:
        curated = not path.startswith(_UGG_PREFIXES)
        links.append(
            SourceLink(
                path=path,
                url=_file_url("blob", path),
                origin="curated" if curated else "ugg",
                edit_url=_file_url("edit", path) if curated else None,
            )
        )
    return links


def contribute_url(question: str, reply: str, paths: list[str]) -> str | None:
    """Prefilled new-issue link. None when the answer used no repo files.

    The answer is shortened until the whole URL is under 8 KB.
    """
    if not paths:
        return None

    endpoint = f"{settings.data_repo_url.rstrip('/')}/issues/new"
    title = " ".join(question.split()) or "Suggest a data change"
    files = "\n".join(f"- {path}" for path in paths)
    question_text = question.strip()

    def assemble(answer: str) -> str:
        body = (
            f"Question:\n{question_text}\n\n"
            f"Answer:\n{answer}\n\n"
            f"Files:\n{files}\n"
        )
        return f"{endpoint}?{urlencode({'title': title, 'body': body})}"

    answer = reply.strip()
    full = assemble(answer)
    if len(full) < _MAX_URL_CHARS:
        return full

    mark = "[truncated]"
    best = ""
    low = 0
    high = len(answer)
    while low <= high:
        mid = (low + high) // 2
        candidate = answer[:mid].rstrip()
        if mid < len(answer):
            candidate = f"{candidate}\n{mark}" if candidate else mark
        if len(assemble(candidate)) < _MAX_URL_CHARS:
            best = candidate
            low = mid + 1
        else:
            high = mid - 1
    return assemble(best)
