from datetime import datetime, timedelta
from types import SimpleNamespace

from app.routers import storefront_offer_pages as op

NOW = datetime(2026, 11, 7, 12, 0, 0)  # UTC, naive like the stored values


def _row(status, start_h, end_h):
    return SimpleNamespace(status=status, starts_at=NOW + timedelta(hours=start_h), ends_at=NOW + timedelta(hours=end_h))


def test_scheduled_before_start_is_upcoming_not_public():
    r = _row("scheduled", 48, 100)
    assert op._state(r, NOW) == "upcoming"
    assert op._is_public(r, NOW) is False  # popups and the like only use running offers


def test_scheduled_inside_its_dates_is_live_and_after_is_hidden():
    assert op._state(_row("scheduled", -1, 5), NOW) == "live"
    assert op._state(_row("scheduled", -10, -1), NOW) is None


def test_running_is_always_live():
    assert op._state(_row("running", -100, -50), NOW) == "live"
    assert op._state(_row("running", 50, 60), NOW) == "live"


def test_draft_disabled_ended_never_show_even_before_start():
    for st in ("draft", "disabled", "ended"):
        assert op._state(_row(st, 48, 100), NOW) is None
        assert op._state(_row(st, -1, 5), NOW) is None


def test_start_is_written_in_dhaka_time():
    # 18:00 UTC on 10 Nov is midnight 11 Nov in Dhaka (UTC+6)
    assert op._starts_label(datetime(2026, 11, 10, 18, 0)) == "11 Nov 2026, 12:00 AM"
    assert op._starts_label(datetime(2026, 11, 11, 6, 30)) == "11 Nov 2026, 12:30 PM"
