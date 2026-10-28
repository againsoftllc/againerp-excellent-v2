"""Grants + emails secure download links once an order with digital products is paid."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.catalog_product import CatalogProduct
from app.models.catalog_product_digital_file import CatalogProductDigitalFile
from app.models.commerce_order import CommerceOrder
from app.models.commerce_order_digital_download import CommerceOrderDigitalDownload
from app.models.commerce_order_item import CommerceOrderItem
from app.security import new_download_token
from app.services.email_service import send_email

logger = logging.getLogger("app.digital_delivery")


def download_url(token: str) -> str:
    base = get_settings().storefront_public_url.strip().rstrip("/")
    return f"{base}/api/v1/storefront/downloads/{token}"


def grant_downloads_for_order(db: Session, order: CommerceOrder) -> list[CommerceOrderDigitalDownload]:
    """Create one download grant per digital file on this order.

    Idempotent: a payment webhook can fire more than once (retries, both a
    browser return AND an IPN), so a second call for the same order returns
    the grants already made instead of duplicating them.
    """
    existing = (
        db.query(CommerceOrderDigitalDownload)
        .filter(CommerceOrderDigitalDownload.order_id == order.id)
        .all()
    )
    if existing:
        return existing

    items = db.query(CommerceOrderItem).filter(CommerceOrderItem.order_id == order.id).all()
    product_ids = {i.product_id for i in items if i.product_id}
    if not product_ids:
        return []

    products = {
        p.id: p for p in db.query(CatalogProduct).filter(CatalogProduct.id.in_(product_ids)).all()
    }

    now = datetime.utcnow()
    grants: list[CommerceOrderDigitalDownload] = []
    for item in items:
        product = products.get(item.product_id)
        if not product or product.product_type != "digital":
            continue
        files = (
            db.query(CatalogProductDigitalFile)
            .filter(CatalogProductDigitalFile.product_id == product.id)
            .order_by(CatalogProductDigitalFile.sort_order)
            .all()
        )
        for digital_file in files:
            expires_at = (
                now + timedelta(days=digital_file.expires_days) if digital_file.expires_days else None
            )
            grant = CommerceOrderDigitalDownload(
                order_id=order.id,
                order_item_id=item.id,
                digital_file_id=digital_file.id,
                token=new_download_token(),
                max_downloads=digital_file.download_limit,
                expires_at=expires_at,
            )
            db.add(grant)
            grants.append(grant)

    if grants:
        db.commit()
        for grant in grants:
            db.refresh(grant)
    return grants


def _email_body(order: CommerceOrder, grants: list[CommerceOrderDigitalDownload], db: Session) -> tuple[str, str]:
    file_ids = [g.digital_file_id for g in grants]
    files = {
        f.id: f
        for f in db.query(CatalogProductDigitalFile).filter(CatalogProductDigitalFile.id.in_(file_ids)).all()
    }
    rows_html = []
    rows_text = []
    for grant in grants:
        digital_file = files.get(grant.digital_file_id)
        name = digital_file.file_name if digital_file else "Download"
        url = download_url(grant.token)
        limit = f" · usable {grant.max_downloads} time(s)" if grant.max_downloads else ""
        expiry = f" · expires {grant.expires_at:%Y-%m-%d}" if grant.expires_at else ""
        rows_html.append(
            f'<li><a href="{url}">{name}</a>{limit}{expiry}</li>'
        )
        rows_text.append(f"- {name}: {url}{limit}{expiry}")

    html = (
        f"<p>Thanks for your order <b>{order.order_number}</b> — your payment has been confirmed.</p>"
        f"<p>Download your file(s) below:</p><ul>{''.join(rows_html)}</ul>"
        "<p>If a link stops working, sign in to your account's Downloads page for the latest copy.</p>"
    )
    text = (
        f"Thanks for your order {order.order_number} — your payment has been confirmed.\n\n"
        "Download your file(s):\n" + "\n".join(rows_text) +
        "\n\nIf a link stops working, sign in to your account's Downloads page for the latest copy."
    )
    return html, text


def _is_fully_digital_order(db: Session, order: CommerceOrder) -> bool:
    items = db.query(CommerceOrderItem).filter(CommerceOrderItem.order_id == order.id).all()
    product_ids = {i.product_id for i in items if i.product_id}
    if not product_ids:
        return False
    digital_ids = {
        p.id
        for p in db.query(CatalogProduct)
        .filter(CatalogProduct.id.in_(product_ids), CatalogProduct.product_type == "digital")
        .all()
    }
    return digital_ids == product_ids


def _complete_fully_digital_order(db: Session, order: CommerceOrder) -> None:
    """A fully-digital order has nothing left to ship once it's paid — the
    download grant above *is* the delivery. Auto-advance the lifecycle status
    so it doesn't sit at "pending" forever waiting for a physical-fulfillment
    step that will never happen for this order."""
    if order.status != "pending" or not _is_fully_digital_order(db, order):
        return
    from app.services.commerce.commerce_order_service import CommerceOrderService

    order_svc = CommerceOrderService(db)
    for step in ("confirmed", "processing", "completed"):
        order_svc.transition(order.id, step, actor="system", message="Digital order — nothing to ship")


def fulfill_paid_order_digital_downloads(db: Session, order: CommerceOrder) -> None:
    """Grant downloads, email the customer, and close out a fully-digital
    order's lifecycle status. Never raises — a payment webhook must still
    succeed even if delivery/email/status-advance fails; the customer's
    account Downloads page and the admin's own status control are the
    fallback for each half of this respectively."""
    try:
        grants = grant_downloads_for_order(db, order)
        if grants:
            html, text = _email_body(order, grants, db)
            send_email(
                to=order.customer_email,
                subject=f"Your download — Order {order.order_number}",
                html_body=html,
                text_body=text,
            )
    except Exception:
        logger.exception("fulfill_paid_order_digital_downloads failed for order %s", order.id)

    try:
        _complete_fully_digital_order(db, order)
    except Exception:
        logger.exception("_complete_fully_digital_order failed for order %s", order.id)
