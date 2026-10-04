import hashlib

from app.auth.login_success import (
    build_signup_cookie_value,
    hash_email_for_gads,
    parse_signup_cookie,
    render_login_success_page,
    signup_transaction_id,
    valid_email_hash,
    valid_transaction_id,
)


def _set_gads(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "gads_id", "AW-123", raising=False)
    monkeypatch.setattr(settings, "gads_activation_label", "label", raising=False)


def test_signup_transaction_id_is_16_hex():
    tid = signup_transaction_id("user-123")
    assert len(tid) == 16
    int(tid, 16)  # raises ValueError if not valid hex


def test_signup_transaction_id_is_stable_per_user():
    assert signup_transaction_id("user-123") == signup_transaction_id("user-123")
    assert signup_transaction_id("user-123") != signup_transaction_id("user-456")


def test_signup_transaction_id_matches_ids_already_sent_to_google():
    # The id was derived with the ":activation" suffix before the rename; it must not change.
    expected = hashlib.sha256(b"user-123:activation").hexdigest()[:16]
    assert signup_transaction_id("user-123") == expected


def test_valid_transaction_id_accepts_16_lowercase_hex():
    assert valid_transaction_id("a" * 16) == "a" * 16
    assert valid_transaction_id("0" * 16) == "0" * 16
    assert valid_transaction_id("f0e9d8c7b6a54321") == "f0e9d8c7b6a54321"


def test_valid_transaction_id_rejects_invalid():
    assert valid_transaction_id(None) is None
    assert valid_transaction_id("") is None
    assert valid_transaction_id("a" * 15) is None
    assert valid_transaction_id("a" * 17) is None
    assert valid_transaction_id("g" * 16) is None
    assert valid_transaction_id("A" * 16) is None


def test_hash_email_normalizes_case_and_whitespace():
    expected = hashlib.sha256(b"jane@example.com").hexdigest()
    assert hash_email_for_gads("  Jane@Example.COM ") == expected


def test_hash_email_drops_dots_only_for_gmail():
    gmail = hashlib.sha256(b"janedoe@gmail.com").hexdigest()
    assert hash_email_for_gads("Jane.Doe@gmail.com") == gmail
    assert hash_email_for_gads("jane.doe@googlemail.com") == hashlib.sha256(b"janedoe@googlemail.com").hexdigest()
    assert hash_email_for_gads("jane.doe@example.com") == hashlib.sha256(b"jane.doe@example.com").hexdigest()


def test_hash_email_rejects_missing_or_malformed():
    for value in (None, "", "   ", "no-at-sign", "@example.com", "jane@"):
        assert hash_email_for_gads(value) is None


def test_valid_email_hash():
    assert valid_email_hash("a" * 64) == "a" * 64
    for value in (None, "", "a" * 63, "a" * 65, "A" * 64, "g" * 64):
        assert valid_email_hash(value) is None


def test_signup_cookie_roundtrip():
    tid = "a" * 16
    email_hash = "b" * 64
    assert parse_signup_cookie(build_signup_cookie_value(tid, email_hash)) == (tid, email_hash)
    assert parse_signup_cookie(build_signup_cookie_value(tid)) == (tid, None)


def test_parse_signup_cookie_rejects_garbage():
    assert parse_signup_cookie(None) == (None, None)
    assert parse_signup_cookie("") == (None, None)
    assert parse_signup_cookie("not-a-transaction-id") == (None, None)
    assert parse_signup_cookie("1") == (None, None)
    # A bad hash is dropped but the conversion itself is still allowed.
    assert parse_signup_cookie("a" * 16 + ".zzz") == ("a" * 16, None)


def test_render_includes_transaction_id_only_for_valid_id(monkeypatch):
    _set_gads(monkeypatch)

    html = render_login_success_page("a" * 16)
    assert "transaction_id: '" + ("a" * 16) + "'" in html
    assert "send_to: 'AW-123/label'" in html


def test_render_no_conversion_for_none_or_invalid(monkeypatch):
    _set_gads(monkeypatch)

    for value in (None, "", "g" * 16, "A" * 16, "a" * 15):
        html = render_login_success_page(value)
        assert "transaction_id" not in html
        assert "conversion" not in html
        assert "user_data" not in html


def test_render_sets_user_data_before_conversion(monkeypatch):
    _set_gads(monkeypatch)

    html = render_login_success_page("a" * 16, "b" * 64)
    assert "sha256_email_address: '" + ("b" * 64) + "'" in html
    assert html.index("gtag('config'") < html.index("'user_data'") < html.index("'conversion'")


def test_render_omits_user_data_without_or_with_invalid_hash(monkeypatch):
    _set_gads(monkeypatch)

    assert "user_data" not in render_login_success_page("a" * 16)
    assert "user_data" not in render_login_success_page("a" * 16, "not-a-hash")
    assert "user_data" not in render_login_success_page("a" * 16, "x'});alert(1);//")


def test_render_has_no_consent_mode(monkeypatch):
    _set_gads(monkeypatch)

    html = render_login_success_page("a" * 16)
    assert "consent" not in html
    assert html.index("gtag('config'") < html.index("'conversion'")
