from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps.storefront_customer_auth import CustomerAuthContext, get_current_storefront_customer
from app.schemas.storefront_account import (
    AuthMethodResponse,
    AuthSessionResponse,
    CustomerMeRead,
    GoogleAuthConfigResponse,
    GoogleAuthStartResponse,
    GoogleLoginRequest,
    IdentifierRequest,
    LoginPinRequest,
    MeResponse,
    OkResponse,
    RequestOtpResponse,
    SetPinRequest,
    VerifyOtpRequest,
)
from app.services.ecommerce.storefront_customer_auth_service import (
    CustomerAuthError,
    StorefrontCustomerAuthService,
    mask_identifier,
)
from app.services.ecommerce.storefront_google_oauth import (
    build_google_auth_url,
    default_redirect_uri,
    encode_oauth_state,
    exchange_google_code,
    google_client_id,
    google_is_configured,
    google_mode,
    verify_google_access_token,
    verify_google_id_token,
)

router = APIRouter(prefix="/auth", tags=["storefront-auth"])


def _svc(db: Session) -> StorefrontCustomerAuthService:
    return StorefrontCustomerAuthService(db)


def _http(exc: CustomerAuthError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.message)


@router.post("/method", response_model=AuthMethodResponse)
def auth_method(payload: IdentifierRequest, db: Session = Depends(get_db)) -> AuthMethodResponse:
    try:
        normalized, identity, is_registered = _svc(db).get_method(payload.identifier)
    except CustomerAuthError as exc:
        raise _http(exc) from exc
    has_pin = bool(identity and identity.pin_hash and identity.is_active)
    return AuthMethodResponse(
        method="pin" if has_pin else "otp",
        identifier=normalized.identifier,
        identifier_type=normalized.identifier_type,
        masked=mask_identifier(normalized),
        has_pin=has_pin,
        is_registered=is_registered,
    )


@router.post("/request-otp", response_model=RequestOtpResponse)
def request_otp(payload: IdentifierRequest, db: Session = Depends(get_db)) -> RequestOtpResponse:
    try:
        normalized, expires_in, dev_otp = _svc(db).request_otp(payload.identifier)
    except CustomerAuthError as exc:
        raise _http(exc) from exc
    return RequestOtpResponse(
        expires_in=expires_in,
        masked=mask_identifier(normalized),
        development_otp=dev_otp,
    )


@router.post("/verify-otp", response_model=AuthSessionResponse)
def verify_otp(payload: VerifyOtpRequest, db: Session = Depends(get_db)) -> AuthSessionResponse:
    try:
        token, expires_at, customer, identity = _svc(db).verify_otp(
            payload.identifier,
            payload.otp,
            display_name=payload.name,
        )
    except CustomerAuthError as exc:
        raise _http(exc) from exc
    return AuthSessionResponse(
        token=token,
        expires_at=expires_at,
        customer=CustomerMeRead(**StorefrontCustomerAuthService.customer_to_me(customer, identity)),
    )


@router.post("/login-pin", response_model=AuthSessionResponse)
def login_pin(payload: LoginPinRequest, db: Session = Depends(get_db)) -> AuthSessionResponse:
    try:
        token, expires_at, customer, identity = _svc(db).login_pin(payload.identifier, payload.pin)
    except CustomerAuthError as exc:
        raise _http(exc) from exc
    return AuthSessionResponse(
        token=token,
        expires_at=expires_at,
        customer=CustomerMeRead(**StorefrontCustomerAuthService.customer_to_me(customer, identity)),
    )


@router.get("/google/config", response_model=GoogleAuthConfigResponse)
def google_config() -> GoogleAuthConfigResponse:
    return GoogleAuthConfigResponse(
        enabled=google_is_configured(),
        client_id=google_client_id(),
        mode=google_mode(),  # type: ignore[arg-type]
        redirect_uri=default_redirect_uri(),
    )


@router.get("/google/start", response_model=GoogleAuthStartResponse)
def google_start(
    next_path: str = Query("/account", alias="next"),
    redirect_uri: Optional[str] = None,
) -> GoogleAuthStartResponse:
    uri = (redirect_uri or "").strip() or default_redirect_uri()
    try:
        auth_url = build_google_auth_url(redirect_uri=uri, next_path=next_path)
    except CustomerAuthError as exc:
        raise _http(exc) from exc
    return GoogleAuthStartResponse(auth_url=auth_url, state=encode_oauth_state(next_path))


@router.post("/google", response_model=AuthSessionResponse)
def google_login(payload: GoogleLoginRequest, db: Session = Depends(get_db)) -> AuthSessionResponse:
    try:
        if payload.id_token and payload.id_token.strip():
            profile = verify_google_id_token(payload.id_token)
        elif payload.access_token and payload.access_token.strip():
            profile = verify_google_access_token(payload.access_token)
        elif payload.code and payload.code.strip():
            profile = exchange_google_code(
                payload.code,
                (payload.redirect_uri or "").strip() or default_redirect_uri(),
            )
        else:
            raise CustomerAuthError("Send a Google id_token, access_token, or authorization code")
        token, expires_at, customer, identity = _svc(db).login_with_google(
            profile["email"],
            profile.get("name") or "",
        )
    except CustomerAuthError as exc:
        raise _http(exc) from exc
    return AuthSessionResponse(
        token=token,
        expires_at=expires_at,
        customer=CustomerMeRead(**StorefrontCustomerAuthService.customer_to_me(customer, identity)),
    )


@router.get("/me", response_model=MeResponse)
def me(ctx: CustomerAuthContext = Depends(get_current_storefront_customer)) -> MeResponse:
    _session, identity, customer = ctx
    return MeResponse(
        data=CustomerMeRead(**StorefrontCustomerAuthService.customer_to_me(customer, identity)),
    )


@router.post("/logout", response_model=OkResponse)
def logout(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> OkResponse:
    token = ""
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
    _svc(db).logout(token)
    return OkResponse()


@router.put("/pin", response_model=MeResponse)
def set_pin(
    payload: SetPinRequest,
    ctx: CustomerAuthContext = Depends(get_current_storefront_customer),
    db: Session = Depends(get_db),
) -> MeResponse:
    _session, identity, customer = ctx
    try:
        _svc(db).set_pin(identity, payload.pin, payload.confirm_pin)
    except CustomerAuthError as exc:
        raise _http(exc) from exc
    db.refresh(identity)
    return MeResponse(
        data=CustomerMeRead(**StorefrontCustomerAuthService.customer_to_me(customer, identity)),
    )


@router.delete("/pin", response_model=MeResponse)
def clear_pin(
    ctx: CustomerAuthContext = Depends(get_current_storefront_customer),
    db: Session = Depends(get_db),
) -> MeResponse:
    _session, identity, customer = ctx
    _svc(db).clear_pin(identity)
    db.refresh(identity)
    return MeResponse(
        data=CustomerMeRead(**StorefrontCustomerAuthService.customer_to_me(customer, identity)),
    )
