import hashlib
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


def _patch_service(monkeypatch, user_id, is_new_user):
    session = SimpleNamespace(user_id=user_id)

    async def fake_complete(code, state):
        return session, is_new_user

    monkeypatch.setattr(routes.service, "complete_auth_flow", fake_complete)
    return session


def _patch_repo(monkeypatch, email="Dan.Bedrood@gmail.com"):
    captured = []

    async def fake_set_acquisition(user_id, acquisition):
        captured.append({"user_id": user_id, "acquisition": acquisition})
        return None

    async def fake_get_user_by_id(user_id):
        return SimpleNamespace(email=email)

    monkeypatch.setattr(routes.user_repository, "set_acquisition", fake_set_acquisition)
    monkeypatch.setattr(routes.user_repository, "get_user_by_id", fake_get_user_by_id)
    return captured


def _patch_posthog(monkeypatch):
    calls = []

    def fake_record(user_id, properties, ph_id=None):
        calls.append({"user_id": user_id, "properties": properties, "ph_id": ph_id})

    monkeypatch.setattr(routes, "record_user_signed_up", fake_record)
    return calls


async def _callback(cookie_header):
    req = _make_request(cookie_header)
    return await routes.auth_callback(req, code="c", state="s", error=None, error_description=None)


def _cookie_value(resp):
    header = resp.headers.get("set-cookie") or ""
    marker = "sensii_signup="
    if marker not in header:
        return None
    return header.split(marker, 1)[1].split(";", 1)[0]


ATTR_RAW = '{"utm_source":"google","gclid":"test","landing_path":"/","ts":"x","ph_id":"ph-123"}'
ATTR_COOKIE = f"sensii_attr={quote(ATTR_RAW)}"


@pytest.mark.asyncio
async def test_new_account_sets_signup_cookie_stores_acquisition_and_sends_event(monkeypatch):
    _patch_service(monkeypatch, "u-123", True)
    captured = _patch_repo(monkeypatch)
    posthog_calls = _patch_posthog(monkeypatch)

    resp = await _callback(ATTR_COOKIE)

    value = _cookie_value(resp)
    expected_hash = hashlib.sha256(b"danbedrood@gmail.com").hexdigest()
    assert value is not None and value.endswith("." + expected_hash)
    assert captured[0]["user_id"] == "u-123"
    assert captured[0]["acquisition"]["utm_source"] == "google"
    assert captured[0]["acquisition"]["ph_id"] == "ph-123"
    assert posthog_calls[0]["ph_id"] == "ph-123"


@pytest.mark.asyncio
async def test_returning_user_gets_no_signup_cookie_or_side_effects(monkeypatch):
    _patch_service(monkeypatch, "u-123", False)
    captured = _patch_repo(monkeypatch)
    posthog_calls = _patch_posthog(monkeypatch)

    resp = await _callback(ATTR_COOKIE)

    assert _cookie_value(resp) is None
    assert captured == []
    assert posthog_calls == []


@pytest.mark.asyncio
async def test_signup_without_attribution_still_arms_conversion(monkeypatch):
    _patch_service(monkeypatch, "u-123", True)
    captured = _patch_repo(monkeypatch)
    posthog_calls = _patch_posthog(monkeypatch)

    resp = await _callback(None)

    assert _cookie_value(resp) is not None
    assert captured == []
    assert posthog_calls[0]["ph_id"] is None


@pytest.mark.asyncio
async def test_repository_failure_does_not_skip_cookie_or_posthog(monkeypatch):
    _patch_service(monkeypatch, "u-123", True)
    _patch_repo(monkeypatch)
    posthog_calls = _patch_posthog(monkeypatch)

    async def failing_set_acquisition(user_id, acquisition):
        raise RuntimeError("db down")

    monkeypatch.setattr(routes.user_repository, "set_acquisition", failing_set_acquisition)

    resp = await _callback(ATTR_COOKIE)

    assert resp.status_code == 307
    assert _cookie_value(resp) is not None
    assert len(posthog_calls) == 1


@pytest.mark.asyncio
async def test_posthog_failure_does_not_skip_cookie_or_attribution(monkeypatch):
    _patch_service(monkeypatch, "u-123", True)
    captured = _patch_repo(monkeypatch)

    def failing_record(user_id, properties, ph_id=None):
        raise RuntimeError("posthog down")

    monkeypatch.setattr(routes, "record_user_signed_up", failing_record)

    resp = await _callback(ATTR_COOKIE)

    assert resp.status_code == 307
    assert _cookie_value(resp) is not None
    assert len(captured) == 1


@pytest.mark.asyncio
async def test_email_lookup_failure_still_arms_conversion_without_hash(monkeypatch):
    _patch_service(monkeypatch, "u-123", True)
    _patch_repo(monkeypatch)
    _patch_posthog(monkeypatch)

    async def failing_get_user(user_id):
        raise RuntimeError("db down")

    monkeypatch.setattr(routes.user_repository, "get_user_by_id", failing_get_user)

    resp = await _callback(None)

    value = _cookie_value(resp)
    assert value is not None and "." not in value


@pytest.mark.asyncio
async def test_empty_user_id_skips_everything(monkeypatch):
    _patch_service(monkeypatch, None, True)
    captured = _patch_repo(monkeypatch)
    posthog_calls = _patch_posthog(monkeypatch)

    resp = await _callback(ATTR_COOKIE)

    assert _cookie_value(resp) is None
    assert captured == []
    assert posthog_calls == []


@pytest.mark.asyncio
async def test_login_success_consumes_cookie_and_fires_once(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "gads_id", "AW-123", raising=False)
    monkeypatch.setattr(settings, "gads_activation_label", "label", raising=False)

    tid = routes.signup_transaction_id("u-123")
    email_hash = "c" * 64
    req = _make_request(f"{routes.SIGNUP_COOKIE}={tid}.{email_hash}")
    resp = await routes.login_success(req)

    body = resp.body.decode()
    assert f"transaction_id: '{tid}'" in body
    assert f"sha256_email_address: '{email_hash}'" in body
    assert f"{routes.SIGNUP_COOKIE}=" in (resp.headers.get("set-cookie") or "")  # deletion header

    # Without the cookie (e.g. a repeat visit) no conversion is rendered.
    resp = await routes.login_success(_make_request(None))
    assert "conversion" not in resp.body.decode()
    assert resp.headers.get("set-cookie") is None
