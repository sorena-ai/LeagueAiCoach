"""Turn tool-call file paths into links in the open source repos."""

from urllib.parse import quote, urlencode

from langchain_core.messages import ToolMessage
from pydantic import BaseModel

from app.config import settings

# Stay under 8 KB so the prefilled issue URL survives browsers and GitHub.
_MAX_URL_CHARS = 8192


class FileLink(BaseModel):
    """One data file the answer read, on awesome-league-of-legends."""

    path: str
    url: str
    edit_url: str


class RepoLink(BaseModel):
    """One of the two public Sensii repos."""

    name: str
    url: str


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


def file_links(paths: list[str]) -> list[FileLink]:
    """Blob and edit links for every file, all in the data repo."""
    return [
        FileLink(
            path=path,
            url=_file_url("blob", path),
            edit_url=_file_url("edit", path),
        )
        for path in paths
    ]


def repo_links(paths: list[str]) -> list[RepoLink]:
    """The two public repos. Empty when the answer used no data files."""
    if not paths:
        return []
    return [
        RepoLink(
            name="awesome-league-of-legends",
            url=settings.data_repo_url.rstrip("/"),
        ),
        RepoLink(name="LeagueAiCoach", url=settings.agent_repo_url.rstrip("/")),
    ]


def contribute_url(question: str, reply: str, paths: list[str]) -> str | None:
    """Prefilled new-issue link on the data repo. None when no files were read.

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
