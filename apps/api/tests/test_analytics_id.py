from app.routers import storefront_content as sc


class _Db:
    pass


def _id(monkeypatch, raw):
    import app.routers.platform_settings as ps

    monkeypatch.setattr(ps, "get_platform_setting", lambda db, key: raw)
    return sc._analytics_id(_Db(), "seo.google_analytics_id")


def test_plain_id_is_kept(monkeypatch):
    assert _id(monkeypatch, "  G-ABC123XYZ9  ") == "G-ABC123XYZ9"


def test_lowercase_and_pasted_snippet_are_reduced_to_the_id(monkeypatch):
    assert _id(monkeypatch, "g-abc123xyz9") == "G-ABC123XYZ9"
    assert _id(monkeypatch, "gtag('config', 'G-ABC123XYZ9');") == "G-ABC123XYZ9"


def test_anything_that_could_break_out_of_a_script_is_dropped(monkeypatch):
    assert _id(monkeypatch, "'); alert(1); //") == ""
    assert _id(monkeypatch, "GTM-ABCDEF") == ""  # a Tag Manager container is not a GA4 measurement id
    assert _id(monkeypatch, "") == ""
    assert _id(monkeypatch, None) == ""


def _id_with_switch(monkeypatch, raw, switch):
    import app.routers.platform_settings as ps

    values = {"seo.google_analytics_id": raw, "seo.google_analytics_enabled": switch}
    monkeypatch.setattr(ps, "get_platform_setting", lambda db, key: values.get(key))
    return sc._analytics_id(_Db(), "seo.google_analytics_id")


def test_off_switch_sends_no_id_but_keeps_it_saved(monkeypatch):
    assert _id_with_switch(monkeypatch, "G-ABC123XYZ9", "false") == ""
    assert _id_with_switch(monkeypatch, "G-ABC123XYZ9", " OFF ") == ""
    assert _id_with_switch(monkeypatch, "G-ABC123XYZ9", "0") == ""


def test_on_or_missing_switch_means_on(monkeypatch):
    assert _id_with_switch(monkeypatch, "G-ABC123XYZ9", "true") == "G-ABC123XYZ9"
    assert _id_with_switch(monkeypatch, "G-ABC123XYZ9", None) == "G-ABC123XYZ9"  # sites saved before the switch existed stay on
    assert _id_with_switch(monkeypatch, "G-ABC123XYZ9", "") == "G-ABC123XYZ9"
