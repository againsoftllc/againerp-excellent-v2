"""Whether the Live Chat plugin is installed — Workspace → Plugins → Live Chat.

Stored as the single platform_settings key `plugin.live_chat.installed`, the
same pattern as the Bank EMI plugin. Defaults to on — the feature already
works out of the box; an admin uninstalls it only if they don't want the
Inbox (admin) or the chat button (storefront) reachable yet.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.platform_setting import PlatformSetting

LIVE_CHAT_ENABLED_KEY = "plugin.live_chat.installed"


def load_live_chat_enabled(db: Session) -> bool:
    row = db.query(PlatformSetting).filter(PlatformSetting.key == LIVE_CHAT_ENABLED_KEY).first()
    raw = row.value if row else None
    if raw is None or str(raw).strip() == "":
        return True
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}
