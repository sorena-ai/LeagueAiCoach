from app.auth.login_success import (
    activation_transaction_id,
    render_login_success_page,
    valid_transaction_id,
)


def test_activation_transaction_id_is_16_hex():
    tid = activation_transaction_id("user-123")
    assert len(tid) == 16
    int(tid, 16)  # raises ValueError if not valid hex


def test_activation_transaction_id_is_stable_per_user():
    assert activation_transaction_id("user-123") == activation_transaction_id("user-123")
    assert activation_transaction_id("user-123") != activation_transaction_id("user-456")


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


def test_render_includes_transaction_id_only_for_valid_id(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "gads_id", "AW-123", raising=False)
    monkeypatch.setattr(settings, "gads_activation_label", "label", raising=False)

    html = render_login_success_page("a" * 16)
    assert "transaction_id: '" + ("a" * 16) + "'" in html
    assert "send_to: 'AW-123/label'" in html


def test_render_no_conversion_for_none_or_invalid(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "gads_id", "AW-123", raising=False)
    monkeypatch.setattr(settings, "gads_activation_label", "label", raising=False)

    for value in (None, "", "g" * 16, "A" * 16, "a" * 15):
        html = render_login_success_page(value)
        assert "transaction_id" not in html
        assert "conversion" not in html


def test_render_consent_defaults_match_landing(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "gads_id", "AW-123", raising=False)
    monkeypatch.setattr(settings, "gads_activation_label", "label", raising=False)

    html = render_login_success_page("a" * 16)
    regional = html.index("region: EEA")
    global_default = html.index("gtag('consent', 'default', granted)")
    update = html.index("gtag('consent', 'update', choice)")
    config = html.index("gtag('config'")
    assert regional < global_default < update < config
    assert '"DE"' in html and '"GB"' in html and '"CH"' in html
    assert "__EEA_REGIONS__" not in html
