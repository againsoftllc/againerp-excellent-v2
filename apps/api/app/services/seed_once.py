"""Run a bundled content seed (catalog, pages, campaigns, blog) once per database.

These seeders boot with the API. Re-running them on every start re-created
anything the admin had renamed or deleted (a renamed category came back as an
empty duplicate), so each one now records a flag in `platform_settings` after
its first run and is skipped from then on. A database that already holds the
seeded data but predates the flag is simply marked as seeded.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.platform_setting import PlatformSetting


def already_seeded(db: Session, flag: str, *, has_data: bool) -> bool:
    """True when the seed must not run: flagged, or data present (then flag it now)."""
    if db.get(PlatformSetting, flag) is not None:
        return True
    if has_data:
        mark_seeded(db, flag)
        db.commit()
        return True
    return False


def mark_seeded(db: Session, flag: str) -> None:
    if db.get(PlatformSetting, flag) is None:
        db.add(PlatformSetting(key=flag, value="1", description=f"One-time seed '{flag}' has run."))
