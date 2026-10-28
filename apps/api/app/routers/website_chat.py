"""Admin live-chat inbox — website_chat_*."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps.auth import require_write_access
from app.services.ecommerce.website_chat_service import (
    ChatError,
    WebsiteChatService,
)

router = APIRouter(prefix="/chat", tags=["website-chat"])
NO_STORE = "private, no-store"


def _svc(db: Session) -> WebsiteChatService:
    return WebsiteChatService(db)


class ChatMessageRead(BaseModel):
    id: str
    sender: str
    type: str
    text: str
    product_id: Optional[str] = None
    product_snapshot: Optional[Dict[str, Any]] = None
    bundle_snapshot: Optional[Dict[str, Any]] = None
    file_name: Optional[str] = None
    file_url: Optional[str] = None
    file_mime: Optional[str] = None
    file_size: Optional[int] = None
    file_kind: Optional[str] = None
    time: str
    read: bool
    reaction: Optional[str] = None
    reply_to: Optional[Dict[str, Any]] = None


class ChatConversationRead(BaseModel):
    id: str
    client_key: str
    customer_name: str
    customer_email: str
    starred: bool
    status: str = "open"
    unread_count: int = 0
    messages: List[ChatMessageRead] = Field(default_factory=list)
    updated_at: str


class ChatConversationSummary(BaseModel):
    id: str
    client_key: str
    customer_name: str
    customer_email: str
    starred: bool
    status: str = "open"
    unread_count: int = 0
    last_message: Optional[ChatMessageRead] = None
    updated_at: str


class ChatConversationListMeta(BaseModel):
    count: int
    unread_total: int


class ChatConversationListResponse(BaseModel):
    data: List[ChatConversationSummary]
    meta: ChatConversationListMeta


class ChatConversationResponse(BaseModel):
    data: ChatConversationRead


class ChatReactionUpdate(BaseModel):
    emoji: Optional[str] = Field(default=None, max_length=16)


class ChatMessageCreate(BaseModel):
    text: str = Field(default="", max_length=8000)
    type: str = Field(default="text", max_length=16)
    product_id: Optional[str] = Field(default=None, max_length=36)
    product_snapshot: Optional[Dict[str, Any]] = None
    bundle_snapshot: Optional[Dict[str, Any]] = None
    file_name: Optional[str] = Field(default=None, max_length=255)
    file_url: Optional[str] = None
    file_mime: Optional[str] = Field(default=None, max_length=120)
    file_size: Optional[int] = None
    file_kind: Optional[str] = Field(default=None, max_length=32)
    reply_to_id: Optional[str] = Field(default=None, max_length=36)


class ChatOrderCard(BaseModel):
    id: str
    order_number: str
    status: str
    time: str
    product_name: str = ""
    product_image: str = ""
    product_price: float = 0
    action: str = "Review"
    tracking_url: str = ""
    tracking_number: str = ""


class ChatProductCard(BaseModel):
    id: str
    slug: str = ""
    name: str = ""
    image: str = ""
    priceNew: float = 0
    priceOld: float = 0
    discountPct: int = 0
    href: Optional[str] = None


class ChatVoucherCard(BaseModel):
    code: str
    desc: str = ""
    expiry: str = ""


class ChatContextRead(BaseModel):
    orders: List[ChatOrderCard] = Field(default_factory=list)
    products: List[ChatProductCard] = Field(default_factory=list)
    vouchers: List[ChatVoucherCard] = Field(default_factory=list)


class ChatContextResponse(BaseModel):
    data: ChatContextRead


def _payload_from_create(payload: ChatMessageCreate) -> Dict[str, Any]:
    data: Dict[str, Any] = {}
    if payload.product_snapshot:
        data["product"] = payload.product_snapshot
    if payload.bundle_snapshot:
        data["bundle"] = payload.bundle_snapshot
    return data


@router.get("/conversations", response_model=ChatConversationListResponse)
def list_conversations(
    response: Response,
    search: str = Query(default="", max_length=120),
    list_filter: str = Query(default="all", alias="filter", max_length=16),
    db: Session = Depends(get_db),
) -> ChatConversationListResponse:
    response.headers["Cache-Control"] = NO_STORE
    svc = _svc(db)
    rows = svc.list_conversations(search=search, list_filter=list_filter)
    unread_total = sum(svc.unread_count(c) for c in svc.list_conversations(search="", list_filter="all"))
    return ChatConversationListResponse(
        data=[ChatConversationSummary(**svc.to_summary(row)) for row in rows],
        meta=ChatConversationListMeta(count=len(rows), unread_total=unread_total),
    )


@router.get("/conversations/{conversation_id}", response_model=ChatConversationResponse)
def get_conversation(
    conversation_id: str,
    response: Response,
    db: Session = Depends(get_db),
) -> ChatConversationResponse:
    response.headers["Cache-Control"] = NO_STORE
    try:
        convo = _svc(db).get(conversation_id)
    except ChatError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ChatConversationResponse(data=ChatConversationRead(**_svc(db).to_dict(convo)))


@router.get("/conversations/{conversation_id}/context", response_model=ChatContextResponse)
def get_conversation_context(
    conversation_id: str,
    response: Response,
    products_q: str = Query(default="", max_length=120),
    db: Session = Depends(get_db),
) -> ChatContextResponse:
    response.headers["Cache-Control"] = NO_STORE
    try:
        convo = _svc(db).get(conversation_id)
    except ChatError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    raw = _svc(db).conversation_context(convo, products_q=products_q)
    return ChatContextResponse(data=ChatContextRead(**raw))


@router.post("/conversations/{conversation_id}/messages", response_model=ChatConversationResponse)
def post_admin_message(
    conversation_id: str,
    payload: ChatMessageCreate,
    response: Response,
    db: Session = Depends(get_db),
    _: object = Depends(require_write_access),
) -> ChatConversationResponse:
    response.headers["Cache-Control"] = NO_STORE
    try:
        convo = _svc(db).get(conversation_id)
        _svc(db).add_admin_message(
            convo,
            text=payload.text,
            message_type=payload.type,
            product_id=payload.product_id,
            file_name=payload.file_name,
            file_url=payload.file_url,
            file_mime=payload.file_mime,
            file_size=payload.file_size,
            file_kind=payload.file_kind,
            payload=_payload_from_create(payload),
            reply_to_id=payload.reply_to_id,
        )
        convo = _svc(db).get(conversation_id)
    except ChatError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ChatConversationResponse(data=ChatConversationRead(**_svc(db).to_dict(convo)))


@router.put(
    "/conversations/{conversation_id}/messages/{message_id}/reaction",
    response_model=ChatConversationResponse,
)
def set_admin_message_reaction(
    conversation_id: str,
    message_id: str,
    payload: ChatReactionUpdate,
    response: Response,
    db: Session = Depends(get_db),
    _: object = Depends(require_write_access),
) -> ChatConversationResponse:
    response.headers["Cache-Control"] = NO_STORE
    try:
        convo = _svc(db).get(conversation_id)
        _svc(db).set_reaction(convo, message_id, payload.emoji)
        convo = _svc(db).get(conversation_id)
    except ChatError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ChatConversationResponse(data=ChatConversationRead(**_svc(db).to_dict(convo)))


@router.post("/conversations/{conversation_id}/read", response_model=ChatConversationResponse)
def mark_admin_read(
    conversation_id: str,
    response: Response,
    db: Session = Depends(get_db),
) -> ChatConversationResponse:
    response.headers["Cache-Control"] = NO_STORE
    try:
        convo = _svc(db).get(conversation_id)
        _svc(db).mark_read(convo, "admin")
        convo = _svc(db).get(conversation_id)
    except ChatError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ChatConversationResponse(data=ChatConversationRead(**_svc(db).to_dict(convo)))


@router.post("/conversations/{conversation_id}/star", response_model=ChatConversationResponse)
def toggle_admin_star(
    conversation_id: str,
    response: Response,
    db: Session = Depends(get_db),
    _: object = Depends(require_write_access),
) -> ChatConversationResponse:
    response.headers["Cache-Control"] = NO_STORE
    try:
        convo = _svc(db).get(conversation_id)
        convo = _svc(db).toggle_star(convo)
        convo = _svc(db).get(conversation_id)
    except ChatError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ChatConversationResponse(data=ChatConversationRead(**_svc(db).to_dict(convo)))
