"""Shape of a policy document, mirroring the storefront's PolicyDoc type.

Validating the blocks here means the editor cannot save something the page
cannot render — the failure shows up on save, not as a broken public page.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, model_validator


class PolicyBlock(BaseModel):
    """Exactly one of these is set: paragraph, bold lead-in, bullets, numbers."""

    p: Optional[str] = None
    b: Optional[str] = None
    ul: Optional[List[str]] = None
    ol: Optional[List[str]] = None

    @model_validator(mode="after")
    def _exactly_one(self) -> "PolicyBlock":
        filled = [k for k in ("p", "b", "ul", "ol") if getattr(self, k) is not None]
        if len(filled) != 1:
            raise ValueError("a block must set exactly one of p, b, ul, ol")
        return self


class PolicySection(BaseModel):
    n: int = 0
    title: str = ""
    # Trailing sections such as a disclaimer carry no number.
    unnumbered: bool = False
    blocks: List[PolicyBlock] = Field(default_factory=list)


class PolicyDoc(BaseModel):
    title: str = ""
    updated: str = ""
    reviewer: str = ""
    reviewer_suffix: str = Field(default="", alias="reviewerSuffix")
    intro: List[str] = Field(default_factory=list)
    sections: List[PolicySection] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class PolicyPageRead(BaseModel):
    slug: str
    doc: PolicyDoc
    updated_at: Optional[datetime] = None


class PolicyPageUpdate(BaseModel):
    doc: PolicyDoc


class PolicyPageResponse(BaseModel):
    data: PolicyPageRead


class PolicyPageListResponse(BaseModel):
    data: List[PolicyPageRead]
