from types import SimpleNamespace
from urllib.parse import quote

import pytest
from starlette.requests import Request

from app.auth import routes


def _make_request(cookie_header: str | None) -> Request:
    headers = []
    if cookie_header is not None:
        headers.append((b"cookie", cookie_header.encode("utf-8")))
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/auth/callback",
        "headers": headers,
        "query_string": b"",
        "scheme": "https",
        "server": ("testserver", 443),
        "client": ("testclient", 12345),
    }
    return Request(scope)


def _patch_service(monkeypatch, user_id, is_first_login):
    session = SimpleNamespace(user_id=user_id)

    async def fake_complete(code, state):
        return session, is_first_login

    monkeypatch.setattr(routes.service, "complete_auth_flow", fake_complete)
    return session


def _patch_repo(monkeypatch):
    captured = []

    async def fake_set_acquisition(user_id, acquisition):
        captured.append({"user_id": user_id, "acquisition": acquisition})
        return None

    monkeypatch.setattr(routes.user_repository, "set_acquisition", fake_set_acquisition)
    return captured


def _patch_posthog(monkeypatch):
    calls = []

    def fake_record(user_id, properties, ph_id=None):
        calls.append({"user_id": user_id, "properties": properties, "ph_id": ph_id})

    monkeypatch.setattr(routes, "record_user_activated", fake_record)
    return calls


ATTR_RAW = '{"utm_source":"google","gclid":"test","landing_path":"/","ts":"x","ph_id":"ph-123"}'


@pytest.mark.asyncio
async def test_first_login_sets_cookie_and_stores_acquisition(monkeypatch):
    _patch_service(monkeypatch, "u-123", True)
    captured = _patch_repo(monkeypatch)
    posthog_calls = _patch_posthog(monkeypatch)

    req = _make_request(f"sensii_attr={quote(ATTR_RAW)}; sensii_consent=granted")
    resp = await routes.auth_callback(req, code="c", state="s", error=None, error_description=None)

    assert "sensii_activation=" in (resp.headers.get("set-cookie") or "")
    assert captured[0]["user_id"] == "u-123"
    assert captured[0]["acquisition"]["utm_source"] == "google"
    assert captured[0]["acquisition"]["ph_id"] == "ph-123"
    assert posthog_calls[0]["ph_id"] == "ph-123"


@pytest.mark.asyncio
async def test_repository_exception_still_returns_redirect(monkeypatch):
    _patch_service(monkeypatch, "u-123", True)
    _patch_posthog(monkeypatch)

    async def failing_set_acquisition(user_id, acquisition):
        raise RuntimeError("db down")

    monkeypatch.setattr(routes.user_repository, "set_acquisition", failing_set_acquisition)

    req = _make_request(f"sensii_attr={quote(ATTR_RAW)}")
    resp = await routes.auth_callback(req, code="c", state="s", error=None, error_description=None)

    assert resp.status_code == 307
    assert "sensii_activation=" in (resp.headers.get("set-cookie") or "")


@pytest.mark.asyncio
async def test_consent_not_granted_does_not_call_posthog(monkeypatch):
    _patch_service(monkeypatch, "u-123", True)
    captured = _patch_repo(monkeypatch)
    posthog_calls = _patch_posthog(monkeypatch)

    req = _make_request(f"sensii_attr={quote(ATTR_RAW)}")
    await routes.auth_callback(req, code="c", state="s", error=None, error_description=None)

    assert len(captured) == 1
    assert posthog_calls == []


@pytest.mark.asyncio
async def test_empty_user_id_skips_everything(monkeypatch):
    _patch_service(monkeypatch, None, True)
    captured = _patch_repo(monkeypatch)
    posthog_calls = _patch_posthog(monkeypatch)

    req = _make_request(f"sensii_attr={quote(ATTR_RAW)}; sensii_consent=granted")
    resp = await routes.auth_callback(req, code="c", state="s", error=None, error_description=None)

    assert "sensii_activation=" not in (resp.headers.get("set-cookie") or "")
    assert captured == []
    assert posthog_calls == []
