from __future__ import annotations

from typing import Any, Dict

from pydantic import BaseModel


class BuilderToolConfigRead(BaseModel):
    tool: str
    customized: bool
    config: Dict[str, Any]


class BuilderToolConfigResponse(BaseModel):
    data: BuilderToolConfigRead


class BuilderToolConfigUpdate(BaseModel):
    config: Dict[str, Any]
