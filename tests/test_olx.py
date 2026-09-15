import pytest

from app.olx import normalize_profile_url


def test_normalize_seller_id():
    assert normalize_profile_url("123_abc") == (
        "https://www.olx.com.br/usuarios/123_abc",
        "123_abc",
    )


def test_reject_external_url():
    with pytest.raises(ValueError):
        normalize_profile_url("https://example.com/usuarios/123")


def test_accept_profile_url():
    url, seller_id = normalize_profile_url("https://www.olx.com.br/usuarios/123?foo=bar")
    assert url == "https://www.olx.com.br/usuarios/123"
    assert seller_id == "123"
