"""Google OAuth for storefront customer login / register.

Client ID enables GIS (id_token). Client secret enables redirect/code exchange.
"""

from __future__ import annotations

import base64
from typing import Any, Dict, Optional
from urllib.parse import urlencode, urlparse

import httpx

from app.config import get_settings
from app.services.ecommerce.storefront_customer_auth_service import CustomerAuthError

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
GOOGLE_SCOPES = "openid email profile"
CALLBACK_PATH = "/api/storefront/auth/session"


def google_client_id() -> str:
    return get_settings().google_oauth_client_id.strip()


def google_client_secret() -> str:
    return get_settings().google_oauth_client_secret.strip()


def google_is_configured() -> bool:
    return bool(google_client_id())


def google_mode() -> str:
    if not google_client_id():
        return "unset"
    if google_client_secret():
        return "redirect"
    return "gis"


def encode_oauth_state(next_path: str) -> str:
    path = _safe_next(next_path)
    raw = path.encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_oauth_state(state: str) -> str:
    if not state:
        return "/account"
    pad = "=" * (-len(state) % 4)
    try:
        path = base64.urlsafe_b64decode(state + pad).decode("utf-8")
    except Exception:
        return "/account"
    return _safe_next(path)


def _safe_next(path: str) -> str:
    value = (path or "").strip() or "/account"
    if not value.startswith("/") or value.startswith("//"):
        return "/account"
    return value


def default_redirect_uri() -> str:
    origin = get_settings().storefront_public_url.strip().rstrip("/")
    return f"{origin}{CALLBACK_PATH}"


def redirect_uri_allowed(uri: str) -> bool:
    parsed = urlparse((uri or "").strip())
    if parsed.scheme not in ("http", "https"):
        return False
    if parsed.path.rstrip("/") != CALLBACK_PATH.rstrip("/"):
        return False
    hosts = {
        "localhost:3000",
        "localhost:3002",
        "127.0.0.1:3000",
        "excellent-web-wheat.vercel.app",
        "www.excellenttechnology.com.bd",
        "excellenttechnology.com.bd",
    }
    settings = get_settings()
    public = urlparse(settings.storefront_public_url.strip())
    if public.netloc:
        hosts.add(public.netloc)
    for origin in settings.cors_origins.split(","):
        host = urlparse(origin.strip()).netloc
        if host:
            hosts.add(host)
    try:
        from app.services.site_cors import get_site_cors_origins

        for origin in get_site_cors_origins(ensure_loaded=True):
            host = urlparse(origin.strip()).netloc
            if host:
                hosts.add(host)
    except Exception:
        pass
    return parsed.netloc in hosts


def build_google_auth_url(*, redirect_uri: str, next_path: str = "/account") -> str:
    client_id = google_client_id()
    if not client_id:
        raise CustomerAuthError(
            "Google login is not configured yet. Set GOOGLE_OAUTH_CLIENT_ID on the API.",
            status_code=503,
        )
    if not redirect_uri_allowed(redirect_uri):
        raise CustomerAuthError("Invalid Google redirect URI", status_code=400)
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": GOOGLE_SCOPES,
        "access_type": "online",
        "include_granted_scopes": "true",
        "prompt": "select_account",
        "state": encode_oauth_state(next_path),
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"


def _email_verified(payload: Dict[str, Any]) -> bool:
    value = payload.get("email_verified")
    if value is True:
        return True
    return str(value or "").lower() in {"true", "1"}


def _profile_from_tokeninfo(payload: Dict[str, Any]) -> Dict[str, str]:
    client_id = google_client_id()
    aud = str(payload.get("aud") or "")
    azp = str(payload.get("azp") or "")
    if client_id not in {aud, azp} and client_id not in aud.split():
        raise CustomerAuthError("Google token was issued for a different app", status_code=401)
    if not _email_verified(payload):
        raise CustomerAuthError("Google email is not verified", status_code=401)
    email = str(payload.get("email") or "").strip().lower()
    if not email:
        raise CustomerAuthError("Google account has no email", status_code=400)
    name = str(payload.get("name") or "").strip()
    return {"email": email, "name": name}


def verify_google_id_token(id_token: str) -> Dict[str, str]:
    token = (id_token or "").strip()
    if not token:
        raise CustomerAuthError("Missing Google credential", status_code=400)
    if not google_client_id():
        raise CustomerAuthError(
            "Google login is not configured yet. Set GOOGLE_OAUTH_CLIENT_ID on the API.",
            status_code=503,
        )
    try:
        with httpx.Client(timeout=12.0) as client:
            res = client.get(GOOGLE_TOKENINFO_URL, params={"id_token": token})
    except httpx.HTTPError as exc:
        raise CustomerAuthError("Could not reach Google", status_code=502) from exc
    if res.status_code != 200:
        raise CustomerAuthError("Google credential is invalid or expired", status_code=401)
    try:
        payload = res.json()
    except ValueError as exc:
        raise CustomerAuthError("Google credential is invalid", status_code=401) from exc
    if not isinstance(payload, dict):
        raise CustomerAuthError("Google credential is invalid", status_code=401)
    return _profile_from_tokeninfo(payload)


GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


def verify_google_access_token(access_token: str) -> Dict[str, str]:
    token = (access_token or "").strip()
    if not token:
        raise CustomerAuthError("Missing Google credential", status_code=400)
    if not google_client_id():
        raise CustomerAuthError(
            "Google login is not configured yet. Set GOOGLE_OAUTH_CLIENT_ID on the API.",
            status_code=503,
        )
    try:
        with httpx.Client(timeout=12.0) as client:
            res = client.get(GOOGLE_TOKENINFO_URL, params={"access_token": token})
    except httpx.HTTPError as exc:
        raise CustomerAuthError("Could not reach Google", status_code=502) from exc
    if res.status_code != 200:
        raise CustomerAuthError("Google credential is invalid or expired", status_code=401)
    try:
        payload = res.json()
    except ValueError as exc:
        raise CustomerAuthError("Google credential is invalid", status_code=401) from exc
    if not isinstance(payload, dict):
        raise CustomerAuthError("Google credential is invalid", status_code=401)
    profile = _profile_from_tokeninfo(payload)
    if profile.get("name"):
        return profile
    try:
        with httpx.Client(timeout=12.0) as client:
            info = client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {token}"},
            )
        if info.status_code == 200:
            body = info.json()
            if isinstance(body, dict):
                name = str(body.get("name") or "").strip()
                if name:
                    profile["name"] = name
    except (httpx.HTTPError, ValueError):
        pass
    return profile


def exchange_google_code(code: str, redirect_uri: str) -> Dict[str, str]:
    if not google_client_id() or not google_client_secret():
        raise CustomerAuthError(
            "Google redirect login needs GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET",
            status_code=503,
        )
    if not redirect_uri_allowed(redirect_uri):
        raise CustomerAuthError("Invalid Google redirect URI", status_code=400)
    try:
        with httpx.Client(timeout=15.0) as client:
            res = client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": (code or "").strip(),
                    "client_id": google_client_id(),
                    "client_secret": google_client_secret(),
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
            )
    except httpx.HTTPError as exc:
        raise CustomerAuthError("Could not reach Google", status_code=502) from exc
    if res.status_code != 200:
        raise CustomerAuthError("Google authorization failed", status_code=401)
    try:
        body = res.json()
    except ValueError as exc:
        raise CustomerAuthError("Google authorization failed", status_code=401) from exc
    id_token = str(body.get("id_token") or "")
    if not id_token:
        raise CustomerAuthError("Google did not return an ID token", status_code=401)
    return verify_google_id_token(id_token)
