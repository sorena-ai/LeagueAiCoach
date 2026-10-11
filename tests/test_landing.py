"""Landing sources, prompt, and the ask route. No live model calls."""

import uuid
from xml.etree import ElementTree as ET

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, ToolMessage

from app.assistant.landing.agent import LandingAnswer, build_landing_turn
from app.assistant.landing.prompts import build_landing_prompt
from app.assistant.landing.sources import collect_source_paths, contribute_url, source_links
from app.routes.landing import _hits, router


def test_collect_source_paths_keeps_first_seen_order():
    messages = [
        {"role": "user", "content": "earlier question"},
        {"role": "assistant", "content": "earlier answer"},
        AIMessage(content=""),
        ToolMessage(
            content="<build />",
            artifact=[
                "champion-builds/aatrox/aatrox-build-top.toml",
                "champion-combos/aatrox.toml",
            ],
            tool_call_id="call_1",
        ),
        ToolMessage(
            content="<champion />",
            artifact=[
                "champion-combos/aatrox.toml",
                "playbook/0.0-general.toml",
            ],
            tool_call_id="call_2",
        ),
    ]
    assert collect_source_paths(messages) == [
        "champion-builds/aatrox/aatrox-build-top.toml",
        "champion-combos/aatrox.toml",
        "playbook/0.0-general.toml",
    ]


def test_source_links_edit_curated_files_only():
    links = source_links(
        [
            "champion-builds/aatrox/aatrox-build-top.toml",
            "champion-counters/aatrox/aatrox-counters-top.toml",
            "champion-combos/aatrox.toml",
            "playbook/0.0-general.toml",
        ]
    )
    by_path = {link.path: link for link in links}
    build = by_path["champion-builds/aatrox/aatrox-build-top.toml"]
    assert build.origin == "ugg"
    assert build.edit_url is None
    assert build.url.endswith("/blob/main/champion-builds/aatrox/aatrox-build-top.toml")

    counters = by_path["champion-counters/aatrox/aatrox-counters-top.toml"]
    assert counters.origin == "ugg"
    assert counters.edit_url is None

    combo = by_path["champion-combos/aatrox.toml"]
    assert combo.origin == "curated"
    assert combo.edit_url.endswith("/edit/main/champion-combos/aatrox.toml")

    playbook = by_path["playbook/0.0-general.toml"]
    assert playbook.origin == "curated"
    assert playbook.edit_url.endswith("/edit/main/playbook/0.0-general.toml")


def test_contribute_url_is_none_without_paths_and_stays_under_8kb():
    assert contribute_url("What runes does Aatrox take?", "Conqueror.", []) is None

    url = contribute_url(
        "q" * 500,
        "a" * 20000,
        [
            "champion-builds/aatrox/aatrox-build-top.toml",
            "playbook/0.0-general.toml",
            "playbook/1.0-top.toml",
            "playbook/2.0.0-top-laning.toml",
            "playbook/2.0.1-top-early-game.toml",
            "playbook/2.0.2-top-mid-game.toml",
            "playbook/2.0.3-top-late-game.toml",
        ],
    )
    assert url is not None
    assert len(url) < 8192
    assert url.startswith(
        "https://github.com/sorena-ai/awesome-league-of-legends/issues/new?"
    )
    assert "champion-builds%2Faatrox%2Faatrox-build-top.toml" in url


def test_build_landing_turn_escapes_question_text():
    xml = build_landing_turn("what runes on aatrox top & why <now>")
    assert "&amp;" in xml
    assert "&lt;" in xml
    assert "<now>" not in xml
    parsed = ET.fromstring(xml)
    assert parsed.findtext("language") == "english"
    assert parsed.findtext("question") == "what runes on aatrox top & why <now>"


def test_landing_prompt_has_no_baked_playbook_and_forbids_paths():
    prompt = build_landing_prompt()
    assert "<playbook" not in prompt
    assert 'Do not write file names, paths, links, or "according to my data".' in prompt


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    _hits.clear()
    with TestClient(app) as test_client:
        yield test_client
    _hits.clear()


@pytest.fixture
def patched_advice(monkeypatch):
    async def fake(session, question, language="english"):
        return LandingAnswer(
            reply="Aatrox top takes Conqueror.",
            source_paths=["champion-builds/aatrox/aatrox-build-top.toml"],
        )

    monkeypatch.setattr("app.routes.landing.get_landing_advice", fake)


def test_ask_returns_sources(client, patched_advice):
    response = client.post(
        "/api/v1/assistant/ask",
        json={"question": "What runes does Aatrox top take?"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["reply"] == "Aatrox top takes Conqueror."
    uuid.UUID(body["session_id"])
    assert body["sources"] == [
        {
            "path": "champion-builds/aatrox/aatrox-build-top.toml",
            "url": (
                "https://github.com/sorena-ai/awesome-league-of-legends/blob/main/"
                "champion-builds/aatrox/aatrox-build-top.toml"
            ),
            "origin": "ugg",
            "edit_url": None,
        }
    ]
    assert body["contribute_url"].startswith(
        "https://github.com/sorena-ai/awesome-league-of-legends/issues/new?"
    )


def test_ask_rejects_a_bad_session_id(client, patched_advice):
    response = client.post(
        "/api/v1/assistant/ask",
        json={"question": "Aatrox runes", "session_id": "not-a-uuid"},
    )
    assert response.status_code == 400


def test_ask_rate_limits_the_ninth_call(client, patched_advice):
    for _ in range(8):
        response = client.post(
            "/api/v1/assistant/ask",
            json={"question": "Aatrox runes"},
        )
        assert response.status_code == 200, response.text
    blocked = client.post(
        "/api/v1/assistant/ask",
        json={"question": "Aatrox runes"},
    )
    assert blocked.status_code == 429
