"""Minimal SMTP email sender.

No SMTP provider is wired into Settings yet, so this reads plain env vars
(SMTP_HOST/PORT/USER/PASSWORD/FROM). When SMTP_HOST is unset — the default —
send_email() logs the message instead of sending it, so callers (payment
webhooks) never fail or block on a missing mail provider.
"""

from __future__ import annotations

import logging
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

logger = logging.getLogger("app.email")


def send_email(*, to: str, subject: str, html_body: str, text_body: str | None = None) -> bool:
    """Best-effort send. Returns True only if it actually went out over SMTP."""
    to = (to or "").strip()
    host = os.environ.get("SMTP_HOST", "").strip()

    if not to:
        logger.warning("send_email: no recipient address, subject=%r", subject)
        return False

    if not host:
        logger.info(
            "send_email: SMTP_HOST not configured — logging instead of sending.\nTo: %s\nSubject: %s\n%s",
            to,
            subject,
            text_body or html_body,
        )
        return False

    port = int(os.environ.get("SMTP_PORT", "587") or "587")
    user = os.environ.get("SMTP_USER", "").strip()
    password = os.environ.get("SMTP_PASSWORD", "")
    from_addr = os.environ.get("SMTP_FROM", "").strip() or user or "no-reply@localhost"
    use_tls = os.environ.get("SMTP_USE_TLS", "true").strip().lower() not in {"0", "false", "no"}

    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = from_addr
    message["To"] = to
    if text_body:
        message.attach(MIMEText(text_body, "plain"))
    message.attach(MIMEText(html_body, "html"))

    try:
        with smtplib.SMTP(host, port, timeout=15) as server:
            if use_tls:
                server.starttls()
            if user:
                server.login(user, password)
            server.sendmail(from_addr, [to], message.as_string())
        return True
    except Exception:
        logger.exception("send_email: failed to send to %s", to)
        return False
