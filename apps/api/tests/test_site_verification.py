import re

from app.routers import storefront_content as sc


class _Db:  # stands in for the session; get_platform_setting is patched below
    pass


def _code(monkeypatch, raw):
    import app.routers.platform_settings as ps

    monkeypatch.setattr(ps, "get_platform_setting", lambda db, key: raw)
    return sc._verification_code(_Db(), "seo.google_site_verification")


def test_plain_token_is_kept(monkeypatch):
    assert _code(monkeypatch, "  abcDEF123_-xyz0123456789  ") == "abcDEF123_-xyz0123456789"


def test_whole_meta_tag_is_reduced_to_its_content(monkeypatch):
    tag = '<meta name="google-site-verification" content="AbC123_dEf-4567890xyz" />'
    assert _code(monkeypatch, tag) == "AbC123_dEf-4567890xyz"
    assert _code(monkeypatch, "<meta name='msvalidate.01' content='0123456789ABCDEF0123456789ABCDEF'>") == "0123456789ABCDEF0123456789ABCDEF"


def test_anything_unsafe_or_empty_is_dropped(monkeypatch):
    assert _code(monkeypatch, "") == ""
    assert _code(monkeypatch, None) == ""
    assert _code(monkeypatch, "short") == ""
    assert _code(monkeypatch, 'abc123456789"><script>alert(1)</script>') == ""
    assert _code(monkeypatch, "has space 1234567890") == ""
