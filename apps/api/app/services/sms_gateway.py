from __future__ import annotations

import logging

import httpx
from sqlalchemy.orm import Session

from app.services.site_store_options import load_site_options

logger = logging.getLogger(__name__)

# bulksmsbd.net's send API — the only gateway Settings → Mail/SMS currently
# offers ("BulkSMS BD"). A GET request with these query params; the response
# body's leading digit is their status code (1002 = success).
BULKSMS_BD_URL = "https://bulksmsbd.net/api/smsapi"


def _site_options(db: Session) -> dict:
    from app.routers.workspace_sites import get_primary_site

    site = get_primary_site(db)
    return load_site_options(getattr(site, "options_json", None) if site else None)


def is_sms_configured(db: Session) -> bool:
    """True once the admin has picked a gateway this service actually
    supports (only BulkSMS BD today, of the three listed under Settings →
    Mail/SMS) and saved an API key for it."""
    options = _site_options(db)
    gateway = (options.get("sms_gateway") or "").strip()
    api_key = (options.get("sms_api_key") or "").strip()
    return gateway == "BulkSMS BD" and bool(api_key)


def send_sms(db: Session, to: str, message: str) -> bool:
    """Send one SMS through the admin-configured gateway.

    Only BulkSMS BD is wired — it's the only option the settings screen
    offers today. Never raises: a flaky or misconfigured gateway degrades to
    "OTP not sent" (the caller turns that into a clear error) rather than a
    500 on the login page.
    """
    options = _site_options(db)
    api_key = (options.get("sms_api_key") or "").strip()
    sender_id = (options.get("sms_sender_id") or "").strip()
    gateway = (options.get("sms_gateway") or "BulkSMS BD").strip()
    if not api_key:
        return False
    if gateway != "BulkSMS BD":
        logger.error("Unsupported SMS gateway configured: %s", gateway)
        return False

    params = {
        "api_key": api_key,
        "type": "text",
        "number": to,
        "senderid": sender_id,
        "message": message,
    }
    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(BULKSMS_BD_URL, params=params)
        response.raise_for_status()
        # BulkSMS BD always answers HTTP 200 — success/failure is only in the
        # body. 1002 is their documented success code; anything else (bad
        # key, no balance, invalid number, ...) is a failure worth logging.
        body = response.json()
        if body.get("response_code") == 1002:
            return True
        logger.error("BulkSMS BD rejected send to %s: %s", to, body)
        return False
    except Exception:
        logger.exception("SMS send failed to %s", to)
        return False
