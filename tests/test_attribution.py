from urllib.parse import quote

from app.auth.attribution import build_signup_properties, parse_attribution_cookie


def test_parse_valid_json():
    raw = (
        '{"utm_source":"google","utm_medium":"display","utm_campaign":"t",'
        '"utm_content":"c","utm_term":"g","gclid":"test","landing_path":"/",'
        '"ts":"2026-10-02T00:00:00.000Z","ph_id":"ph-123"}'
    )
    assert parse_attribution_cookie(raw) == {
        "utm_source": "google",
        "utm_medium": "display",
        "utm_campaign": "t",
        "utm_content": "c",
        "utm_term": "g",
        "gclid": "test",
        "landing_path": "/",
        "ts": "2026-10-02T00:00:00.000Z",
        "ph_id": "ph-123",
    }


def test_parse_url_encoded_json():
    result = parse_attribution_cookie(quote('{"utm_source":"google","gclid":"test"}'))
    assert result == {"utm_source": "google", "gclid": "test"}


def test_parse_malformed():
    assert parse_attribution_cookie("{not json") is None


def test_parse_non_dict():
    assert parse_attribution_cookie("[]") is None
    assert parse_attribution_cookie('"just a string"') is None


def test_parse_unknown_keys_dropped():
    raw = '{"utm_source":"google","evil":"x","nested":{"a":1}}'
    assert parse_attribution_cookie(raw) == {"utm_source": "google"}


def test_parse_values_capped_at_200():
    result = parse_attribution_cookie('{"utm_source":"' + ("a" * 500) + '"}')
    assert result is not None
    assert len(result["utm_source"]) == 200


def test_build_signup_properties_excludes_ph_id_and_ts():
    acquisition = {
        "utm_source": "google",
        "gclid": "test",
        "landing_path": "/",
        "ph_id": "ph-123",
        "ts": "x",
    }
    props = build_signup_properties(acquisition)
    assert props["utm_source"] == "google"
    assert props["gclid"] is True
    assert props["landing_path"] == "/"
    assert "ph_id" not in props
    assert "ts" not in props
