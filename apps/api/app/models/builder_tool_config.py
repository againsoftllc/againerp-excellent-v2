from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class BuilderToolConfig(Base):
    """Admin overrides for one Again Builder tool's slots/labels/defaults.

    One row per tool (id = tool slug, e.g. "pc-builder"). ``config_json`` is
    null until an admin actually edits that tool — the storefront and the
    admin panel both fall back to the tool's built-in defaults until then, so
    an uncustomized install behaves exactly like today's hardcoded data.
    """

    __tablename__ = "plugin_builder_tool_config"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(36), nullable=False, default="default")
    config_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
