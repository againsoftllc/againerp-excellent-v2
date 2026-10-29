from __future__ import annotations

import random
import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.commerce_customer import CommerceCustomer, dump_json, load_json
from app.models.storefront_customer_auth import (
    StorefrontCustomerIdentity,
    StorefrontCustomerSession,
    StorefrontOtpChallenge,
)
from app.security import hash_password, new_session_token, verify_password
from app.services.sms_gateway import is_sms_configured, send_sms

DEFAULT_COMPANY_ID = "default"
# Customer statuses are active | vip | inactive | blocked. Only the last two
# are disabled — a VIP is a paying customer, not a locked-out one.
LOGIN_BLOCKED_STATUSES = {"inactive", "blocked"}
# Used only while no SMS gateway is configured (Settings → Mail/SMS) — once
# one is, request_otp sends a real random code instead and this never fires.
DEFAULT_OTP = "1234"
OTP_TTL_SECONDS = 60 * 60 * 24
SESSION_DAYS = 30
PIN_LENGTH = 4
PASSWORD_MIN_LENGTH = 6
PASSWORD_MAX_FAILED = 5          # wrong passwords in a row ...
PASSWORD_LOCK_MINUTES = 15       # ... lock sign-in for this long since the last attempt

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$")
PHONE_RE = re.compile(r"^(?:\+?880)?01[3-9]\d{8}$")


def collapse_repeated_name(name: str) -> str:
    """Undo first+last join when both sides were the same full name."""
    parts = [p for p in (name or "").split() if p]
    if len(parts) >= 2 and len(parts) % 2 == 0:
        mid = len(parts) // 2
        first = " ".join(parts[:mid])
        second = " ".join(parts[mid:])
        if first.lower() == second.lower():
            return first
    return " ".join(parts) if parts else (name or "")


class CustomerAuthError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class NormalizedIdentifier:
    identifier: str
    identifier_type: Literal["phone", "email"]
    display: str


def normalize_identifier(raw: str) -> NormalizedIdentifier:
    value = (raw or "").strip()
    if not value:
        raise CustomerAuthError("Enter your phone number or email")

    if EMAIL_RE.match(value):
        email = value.lower()
        return NormalizedIdentifier(identifier=email, identifier_type="email", display=email)

    digits = re.sub(r"[\s\-]", "", value)
    if digits.startswith("+880"):
        local = "0" + digits[4:]
    elif digits.startswith("880"):
        local = "0" + digits[3:]
    else:
        local = digits
    if not (local.startswith("01") and len(local) == 11 and local.isdigit()):
        raise CustomerAuthError("Enter a valid phone number (e.g. 01XXXXXXXXX) or email address")
    if local[2] not in "3456789":
        raise CustomerAuthError("Enter a valid phone number (e.g. 01XXXXXXXXX) or email address")

    return NormalizedIdentifier(identifier=local, identifier_type="phone", display=local)


def mask_identifier(normalized: NormalizedIdentifier) -> str:
    value = normalized.display
    if normalized.identifier_type == "email":
        user, _, domain = value.partition("@")
        head = user[:2]
        return f"{head}{'*' * max(len(user) - 2, 2)}@{domain}"
    return f"{value[:3]}{'*' * max(len(value) - 5, 3)}{value[-2:]}"


class StorefrontCustomerAuthService:
    def __init__(self, db: Session):
        self._db = db

    def get_method(
        self, raw_identifier: str
    ) -> Tuple[NormalizedIdentifier, StorefrontCustomerIdentity | None, bool]:
        normalized = normalize_identifier(raw_identifier)
        identity = (
            self._db.query(StorefrontCustomerIdentity)
            .filter(StorefrontCustomerIdentity.identifier == normalized.identifier)
            .first()
        )
        is_registered = bool(identity) or bool(self._find_existing_customer(normalized))
        return normalized, identity, is_registered

    def request_otp(self, raw_identifier: str) -> Tuple[NormalizedIdentifier, int, Optional[str]]:
        """Returns (normalized identifier, TTL, dev_otp).

        `dev_otp` is the code to show in the API response for testing — only
        set when no SMS gateway is configured. Once one is, a real random
        code is generated and texted instead, and this comes back None so it
        never leaks into the response.
        """
        normalized = normalize_identifier(raw_identifier)
        now = datetime.utcnow()
        # Invalidate previous open challenges for this identifier.
        open_challenges = (
            self._db.query(StorefrontOtpChallenge)
            .filter(
                StorefrontOtpChallenge.identifier == normalized.identifier,
                StorefrontOtpChallenge.consumed_at.is_(None),
                StorefrontOtpChallenge.expires_at > now,
            )
            .all()
        )
        for challenge in open_challenges:
            challenge.consumed_at = now

        sms_ready = normalized.identifier_type == "phone" and is_sms_configured(self._db)
        dev_otp: Optional[str] = None
        if sms_ready:
            code = f"{random.randint(0, 9999):04d}"
            sent = send_sms(self._db, normalized.identifier, f"Your Excellent Technology BD verification code is {code}")
            if not sent:
                raise CustomerAuthError("Could not send the verification code — please try again", status_code=502)
        else:
            code = DEFAULT_OTP
            dev_otp = DEFAULT_OTP

        challenge = StorefrontOtpChallenge(
            identifier=normalized.identifier,
            identifier_type=normalized.identifier_type,
            code_hash=hash_password(code),
            expires_at=now + timedelta(seconds=OTP_TTL_SECONDS),
        )
        self._db.add(challenge)
        self._db.commit()
        return normalized, OTP_TTL_SECONDS, dev_otp

    def verify_otp(
        self,
        raw_identifier: str,
        otp: str,
        *,
        display_name: Optional[str] = None,
    ) -> Tuple[str, datetime, CommerceCustomer, StorefrontCustomerIdentity]:
        normalized = normalize_identifier(raw_identifier)
        code = (otp or "").strip()
        if len(code) != PIN_LENGTH or not code.isdigit():
            raise CustomerAuthError(f"Enter the {PIN_LENGTH}-digit verification code")

        now = datetime.utcnow()
        challenge = (
            self._db.query(StorefrontOtpChallenge)
            .filter(
                StorefrontOtpChallenge.identifier == normalized.identifier,
                StorefrontOtpChallenge.consumed_at.is_(None),
            )
            .order_by(StorefrontOtpChallenge.created_at.desc())
            .first()
        )

        if not challenge or challenge.expires_at <= now:
            raise CustomerAuthError("OTP expired — request a new code", status_code=400)
        if challenge.attempts >= challenge.max_attempts:
            raise CustomerAuthError("Too many OTP attempts — request a new code", status_code=400)
        if not verify_password(code, challenge.code_hash):
            challenge.attempts += 1
            self._db.commit()
            hint = f" — use {DEFAULT_OTP} until an SMS gateway is configured" if not is_sms_configured(self._db) else ""
            raise CustomerAuthError(f"Wrong OTP{hint}", status_code=401)

        challenge.consumed_at = now
        identity, customer = self._get_or_create_identity(
            normalized,
            verified_at=now,
            display_name=display_name,
        )
        token, expires_at = self._issue_session(identity, customer)
        self._db.commit()
        return token, expires_at, customer, identity

    def login_with_google(
        self,
        email: str,
        name: str = "",
    ) -> Tuple[str, datetime, CommerceCustomer, StorefrontCustomerIdentity]:
        normalized = normalize_identifier(email)
        if normalized.identifier_type != "email":
            raise CustomerAuthError("Google account must include an email address")
        now = datetime.utcnow()
        display = " ".join((name or "").split()).strip()
        identity, customer = self._get_or_create_identity(
            normalized,
            verified_at=now,
            display_name=display or None,
        )
        if display:
            customer.name = display[:120]
        token, expires_at = self._issue_session(identity, customer)
        self._db.commit()
        return token, expires_at, customer, identity

    def login_pin(self, raw_identifier: str, pin: str) -> Tuple[str, datetime, CommerceCustomer, StorefrontCustomerIdentity]:
        normalized = normalize_identifier(raw_identifier)
        code = (pin or "").strip()
        if len(code) != PIN_LENGTH or not code.isdigit():
            raise CustomerAuthError(f"Enter your {PIN_LENGTH}-digit PIN")

        identity = (
            self._db.query(StorefrontCustomerIdentity)
            .filter(StorefrontCustomerIdentity.identifier == normalized.identifier)
            .first()
        )
        if not identity or not identity.pin_hash:
            raise CustomerAuthError("PIN not set — login with OTP", status_code=400)
        if not identity.is_active:
            raise CustomerAuthError("Account is inactive", status_code=403)

        if not verify_password(code, identity.pin_hash):
            identity.failed_pin_attempts += 1
            self._db.commit()
            raise CustomerAuthError("Wrong PIN — try again, or login with OTP", status_code=401)

        identity.failed_pin_attempts = 0
        if not identity.verified_at:
            identity.verified_at = datetime.utcnow()
        customer = self._db.get(CommerceCustomer, identity.customer_id)
        if not customer or customer.status in LOGIN_BLOCKED_STATUSES:
            raise CustomerAuthError("Customer account is not available", status_code=403)

        token, expires_at = self._issue_session(identity, customer)
        self._db.commit()
        return token, expires_at, customer, identity

    # ── Password sign-in (used while OTP is switched off) ────────────────────────────────────────────
    @staticmethod
    def _check_password_rules(password: str) -> str:
        pw = password or ""
        if len(pw) < PASSWORD_MIN_LENGTH:
            raise CustomerAuthError(f"Password must be at least {PASSWORD_MIN_LENGTH} characters")
        if not pw.strip():
            raise CustomerAuthError("Password cannot be only spaces")
        return pw

    def register_password(
        self, *, name: str, phone: str, email: Optional[str], password: str
    ) -> Tuple[str, datetime, CommerceCustomer, StorefrontCustomerIdentity]:
        phone_id = normalize_identifier(phone)
        if phone_id.identifier_type != "phone":
            raise CustomerAuthError("Enter a valid mobile number (01XXXXXXXXX)")
        clean_name = " ".join((name or "").split()).strip()
        if not clean_name:
            raise CustomerAuthError("Enter your name")
        pw = self._check_password_rules(password)

        email_id: Optional[NormalizedIdentifier] = None
        if email and email.strip():
            email_id = normalize_identifier(email)
            if email_id.identifier_type != "email":
                raise CustomerAuthError("Enter a valid email address")

        for ident, label in ((phone_id, "mobile number"), (email_id, "email")):
            if ident is None:
                continue
            taken = (
                self._db.query(StorefrontCustomerIdentity)
                .filter(StorefrontCustomerIdentity.identifier == ident.identifier)
                .first()
            )
            if taken:
                raise CustomerAuthError(f"An account with this {label} already exists. Please log in.", status_code=409)

        # No phone check happens here (that is what OTP is for), so a new customer record is always made;
        # an older guest-checkout record with the same phone is deliberately not attached to this account.
        customer = self._create_customer(phone_id, display_name=clean_name, source="storefront password sign-up")
        if email_id:
            customer.email = email_id.identifier
        hashed = hash_password(pw)
        identity = StorefrontCustomerIdentity(
            customer_id=customer.id,
            identifier=phone_id.identifier,
            identifier_type="phone",
            display_identifier=phone_id.display,
            password_hash=hashed,
            is_active=True,
        )
        self._db.add(identity)
        if email_id:
            self._db.add(
                StorefrontCustomerIdentity(
                    customer_id=customer.id,
                    identifier=email_id.identifier,
                    identifier_type="email",
                    display_identifier=email_id.display,
                    password_hash=hashed,
                    is_active=True,
                )
            )
        self._db.flush()
        token, expires_at = self._issue_session(identity, customer)
        self._db.commit()
        return token, expires_at, customer, identity

    def login_password(
        self, raw_identifier: str, password: str
    ) -> Tuple[str, datetime, CommerceCustomer, StorefrontCustomerIdentity]:
        normalized = normalize_identifier(raw_identifier)
        wrong = CustomerAuthError("Wrong phone/email or password", status_code=401)
        identity = (
            self._db.query(StorefrontCustomerIdentity)
            .filter(StorefrontCustomerIdentity.identifier == normalized.identifier)
            .first()
        )
        if not identity:
            raise wrong
        if not identity.is_active:
            raise CustomerAuthError("Account is inactive", status_code=403)
        if not identity.password_hash:
            raise CustomerAuthError(
                "This account has no password yet. Please contact us to set one.", status_code=400
            )
        if (
            (identity.failed_password_attempts or 0) >= PASSWORD_MAX_FAILED
            and identity.updated_at
            and identity.updated_at > datetime.utcnow() - timedelta(minutes=PASSWORD_LOCK_MINUTES)
        ):
            raise CustomerAuthError(
                f"Too many wrong attempts. Try again in {PASSWORD_LOCK_MINUTES} minutes.", status_code=429
            )
        if not verify_password(password or "", identity.password_hash):
            identity.failed_password_attempts = (identity.failed_password_attempts or 0) + 1
            self._db.commit()
            raise wrong

        identity.failed_password_attempts = 0
        customer = self._db.get(CommerceCustomer, identity.customer_id)
        if not customer or customer.status in LOGIN_BLOCKED_STATUSES:
            raise CustomerAuthError("Customer account is not available", status_code=403)
        token, expires_at = self._issue_session(identity, customer)
        self._db.commit()
        return token, expires_at, customer, identity

    def set_password(
        self,
        identity: StorefrontCustomerIdentity,
        password: str,
        confirm_password: str,
        current_password: Optional[str] = None,
    ) -> None:
        pw = self._check_password_rules(password)
        if pw != confirm_password:
            raise CustomerAuthError("Passwords do not match")
        if identity.password_hash and not verify_password(current_password or "", identity.password_hash):
            raise CustomerAuthError("Your current password is not right", status_code=401)
        hashed = hash_password(pw)
        # the phone and email identities of one customer share the password
        for row in self._db.query(StorefrontCustomerIdentity).filter(
            StorefrontCustomerIdentity.customer_id == identity.customer_id
        ):
            row.password_hash = hashed
            row.failed_password_attempts = 0
        self._db.commit()

    def set_pin(self, identity: StorefrontCustomerIdentity, pin: str, confirm_pin: str) -> None:
        if pin != confirm_pin:
            raise CustomerAuthError("PINs do not match")
        if len(pin) != PIN_LENGTH or not pin.isdigit():
            raise CustomerAuthError(f"PIN must be exactly {PIN_LENGTH} digits")
        identity.pin_hash = hash_password(pin)
        identity.failed_pin_attempts = 0
        self._db.commit()

    def clear_pin(self, identity: StorefrontCustomerIdentity) -> None:
        identity.pin_hash = None
        identity.failed_pin_attempts = 0
        self._db.commit()

    def logout(self, token: str) -> None:
        if not token:
            return
        self._db.query(StorefrontCustomerSession).filter(StorefrontCustomerSession.token == token).delete()
        self._db.commit()

    def get_session(self, token: str) -> Optional[Tuple[StorefrontCustomerSession, StorefrontCustomerIdentity, CommerceCustomer]]:
        if not token:
            return None
        session = (
            self._db.query(StorefrontCustomerSession)
            .filter(
                StorefrontCustomerSession.token == token,
                StorefrontCustomerSession.expires_at > datetime.utcnow(),
            )
            .first()
        )
        if not session:
            return None
        identity = self._db.get(StorefrontCustomerIdentity, session.identity_id)
        customer = self._db.get(CommerceCustomer, session.customer_id)
        if (
            not identity
            or not identity.is_active
            or not customer
            or customer.status in LOGIN_BLOCKED_STATUSES
        ):
            return None
        return session, identity, customer

    def _issue_session(
        self,
        identity: StorefrontCustomerIdentity,
        customer: CommerceCustomer,
    ) -> Tuple[str, datetime]:
        expires_at = datetime.utcnow() + timedelta(days=SESSION_DAYS)
        token = new_session_token()
        self._db.add(
            StorefrontCustomerSession(
                identity_id=identity.id,
                customer_id=customer.id,
                token=token,
                expires_at=expires_at,
            )
        )
        self._db.flush()
        return token, expires_at

    def _get_or_create_identity(
        self,
        normalized: NormalizedIdentifier,
        *,
        verified_at: datetime,
        display_name: Optional[str] = None,
    ) -> Tuple[StorefrontCustomerIdentity, CommerceCustomer]:
        identity = (
            self._db.query(StorefrontCustomerIdentity)
            .filter(StorefrontCustomerIdentity.identifier == normalized.identifier)
            .first()
        )
        if identity:
            customer = self._db.get(CommerceCustomer, identity.customer_id)
            if not customer:
                customer = self._create_customer(normalized, display_name=display_name)
                identity.customer_id = customer.id
            identity.verified_at = verified_at
            identity.is_active = True
            identity.display_identifier = normalized.display
            self._db.flush()
            return identity, customer

        customer = self._find_existing_customer(normalized) or self._create_customer(
            normalized, display_name=display_name
        )
        identity = StorefrontCustomerIdentity(
            customer_id=customer.id,
            identifier=normalized.identifier,
            identifier_type=normalized.identifier_type,
            display_identifier=normalized.display,
            verified_at=verified_at,
            is_active=True,
        )
        self._db.add(identity)
        self._db.flush()
        return identity, customer

    def _find_existing_customer(self, normalized: NormalizedIdentifier) -> Optional[CommerceCustomer]:
        if normalized.identifier_type == "email":
            return (
                self._db.query(CommerceCustomer)
                .filter(CommerceCustomer.email == normalized.identifier)
                .first()
            )
        phone_digits = "".join(ch for ch in normalized.identifier if ch.isdigit())[-11:]
        candidates = (
            self._db.query(CommerceCustomer)
            .filter(CommerceCustomer.phone != "")
            .order_by(CommerceCustomer.created_at.desc())
            .limit(200)
            .all()
        )
        for row in candidates:
            row_digits = "".join(ch for ch in row.phone if ch.isdigit())[-11:]
            if row_digits and row_digits == phone_digits:
                return row
        return None

    def _create_customer(
        self,
        normalized: NormalizedIdentifier,
        *,
        display_name: Optional[str] = None,
        source: str = "storefront OTP",
    ) -> CommerceCustomer:
        cleaned_name = " ".join((display_name or "").split()).strip()
        if normalized.identifier_type == "email":
            email = normalized.identifier
            phone = ""
            name = cleaned_name or email.split("@")[0].replace(".", " ").title() or "Customer"
        else:
            email = ""
            phone = normalized.display
            name = cleaned_name or f"Customer {phone[-4:]}"

        code = f"SF-{new_session_token()[:8].upper()}"
        while self._db.query(CommerceCustomer).filter(CommerceCustomer.customer_code == code).first():
            code = f"SF-{new_session_token()[:8].upper()}"

        row = CommerceCustomer(
            id=str(uuid.uuid4()),
            company_id=DEFAULT_COMPANY_ID,
            customer_code=code,
            name=name,
            phone=phone,
            email=email,
            city="",
            region="",
            country="Bangladesh",
            customer_since=date.today(),
            status="active",
            group="retail",
            tags_json=dump_json(["storefront"]),
            timeline_json=dump_json(
                [
                    {
                        "id": f"tl_{uuid.uuid4().hex[:8]}",
                        "type": "status_change",
                        "title": f"Registered via {source}",
                        "actor": "Storefront",
                        "actorInitials": "SF",
                        "at": datetime.utcnow().isoformat() + "Z",
                    }
                ]
            ),
        )
        # party_id is NOT NULL in this schema: link / create the customer's Party before the first insert
        from app.services.parties.commerce_party_bridge import ensure_party_for_customer

        ensure_party_for_customer(self._db, row)
        self._db.add(row)
        self._db.flush()
        return row

    @staticmethod
    def customer_to_me(
        customer: CommerceCustomer,
        identity: StorefrontCustomerIdentity,
    ) -> dict:
        return {
            "id": customer.id,
            "customer_code": customer.customer_code,
            "name": collapse_repeated_name(customer.name),
            "phone": customer.phone or (identity.display_identifier if identity.identifier_type == "phone" else ""),
            "email": customer.email or (identity.display_identifier if identity.identifier_type == "email" else ""),
            "profile_image": customer.profile_image,
            "city": customer.city or "",
            "region": customer.region or "",
            "country": customer.country or "Bangladesh",
            "reward_points": customer.reward_points or 0,
            "total_orders": customer.total_orders or 0,
            "wallet_balance": customer.wallet_balance,
            "has_pin": bool(identity.pin_hash),
            "has_password": bool(identity.password_hash),
            "identifier": identity.display_identifier or identity.identifier,
            "identifier_type": identity.identifier_type,
            "assigned_staff": customer.assigned_staff,
        }

    @staticmethod
    def load_addresses(customer: CommerceCustomer) -> list:
        return load_json(customer.addresses_json, [])
