"""Production storefront checkout — cart to commerce order (STEP 06)."""

from __future__ import annotations

import json
import secrets
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, List, Optional

from sqlalchemy.orm import Session

from app.models.auth_user import AuthUser
from app.models.commerce_customer import CommerceCustomer, dump_json, load_json
from app.models.commerce_order import CommerceOrder
from app.models.commerce_order_item import CommerceOrderItem
from app.models.finance import FinancePayment, FinanceReceivable
from app.models.inventory_warehouse import InventoryWarehouse
from app.models.storefront_cart import StorefrontCart, StorefrontCartItem
from app.models.commerce_order_item import CommerceOrderItem
from app.services.ecommerce.checkout_constants import (
    DEFAULT_COMPANY_ID,
    PAYMENT_LABELS,
)
from app.services.ecommerce.checkout_tax_availability import (
    resolve_tax_amount,
    shipping_is_taxable,
)
from app.services.marketing.coupon_service import (
    CouponError,
    record_coupon_redemption,
    resolve_coupon_discount,
)
from app.services.ecommerce.checkout_payment_plugin import PreparedPayment, get_payment_plugin
from app.services.ecommerce.checkout_payment_availability import (
    is_payment_method_allowed,
    payment_label_overrides,
    payment_options_as_dicts,
)
from app.services.ecommerce.checkout_shipping_availability import (
    is_shipping_method_allowed,
    pickup_point_label,
    resolve_shipping_amount,
    shipping_options_payload,
)
from app.services.ecommerce.storefront_cart_service import CartError, StorefrontCartService
from app.models.platform_setting import PlatformSetting


def _loyalty_enabled(db: Session) -> bool:
    """Star Points / loyalty on checkout — default OFF until Marketing setting is enabled."""
    row = (
        db.query(PlatformSetting)
        .filter(PlatformSetting.key == "marketing.loyalty")
        .first()
    )
    if row is None or row.value is None or str(row.value).strip() == "":
        return False
    return str(row.value).strip().lower() in {"1", "true", "yes", "on"}


def _checkout_notice_enabled(db: Session) -> bool:
    """Off by default — the notice bar only shows once an admin turns it on."""
    row = (
        db.query(PlatformSetting)
        .filter(PlatformSetting.key == "checkout.notice_enabled")
        .first()
    )
    if row is None or row.value is None or str(row.value).strip() == "":
        return False
    return str(row.value).strip().lower() in {"1", "true", "yes", "on"}


def _checkout_notice_text(db: Session) -> str:
    row = (
        db.query(PlatformSetting)
        .filter(PlatformSetting.key == "checkout.notice_text")
        .first()
    )
    if row is None or row.value is None:
        return ""
    return str(row.value)


class CheckoutError(ValueError):
    """Checkout validation or placement failure."""


def compose_person_name(first_name: str, last_name: str) -> str:
    """Join billing names without doubling a single full-name field."""
    first = " ".join((first_name or "").split()).strip()
    last = " ".join((last_name or "").split()).strip()
    dummy = last.lower() in {"", ".", "-", "_"}
    if dummy or last.lower() == first.lower():
        return first
    if first.lower().endswith(f" {last.lower()}"):
        return first
    return f"{first} {last}".strip()


@dataclass(frozen=True)
class CheckoutAddress:
    first_name: str
    last_name: str
    email: str
    phone: str
    line1: str
    city: str
    region: str = ""
    postal_code: str = ""
    country: str = "Bangladesh"


@dataclass(frozen=True)
class CheckoutPlaceRequest:
    billing: CheckoutAddress
    shipping: CheckoutAddress
    shipping_method: str = "standard"
    payment_method: str = "cod"
    coupon_code: Optional[str] = None
    notes: Optional[str] = None
    customer_id: Optional[str] = None
    pickup_point: Optional[str] = None


@dataclass(frozen=True)
class CheckoutTotals:
    subtotal: Decimal
    discount: Decimal
    tax: Decimal
    shipping: Decimal
    grand_total: Decimal
    coupon_code: Optional[str]


@dataclass(frozen=True)
class CheckoutPlaceResult:
    order: CommerceOrder
    prepared_payment: PreparedPayment
    invoice_id: Optional[str]
    payment_record_id: Optional[str]


class StorefrontCheckoutService:
    def __init__(self, db: Session, *, allow_out_of_stock: bool = False) -> None:
        self._db = db
        self._cart_svc = StorefrontCartService(db, allow_out_of_stock=allow_out_of_stock)

    def get_options(self) -> dict[str, Any]:
        shipping = shipping_options_payload(self._db)
        return {
            **shipping,
            "payment_methods": payment_options_as_dicts(self._db),
            "reward_points_enabled": _loyalty_enabled(self._db),
            "checkout_notice_enabled": _checkout_notice_enabled(self._db),
            "checkout_notice_text": _checkout_notice_text(self._db),
            "emi_banks": [
                {"id": "city", "name": "City Bank", "months": [3, 6, 9, 12]},
                {"id": "brac", "name": "BRAC Bank", "months": [3, 6, 12]},
                {"id": "ebl", "name": "Eastern Bank", "months": [6, 12]},
                {"id": "dutch", "name": "Dutch-Bangla Bank", "months": [3, 6, 9, 12]},
                {"id": "scb", "name": "Standard Chartered", "months": [6, 12]},
            ],
        }

    def preview(
        self,
        cart: StorefrontCart,
        *,
        shipping_method: str = "standard",
        coupon_code: Optional[str] = None,
        district: str = "",
    ) -> CheckoutTotals:
        subtotal = sum((line.unit_price * line.quantity for line in cart.items), Decimal("0"))
        code = (coupon_code or cart.coupon_code or "").strip() or None
        # A Ready Build's whole-build discount was set on the cart as a lump
        # sum when its parts were added (see add_ready_build_to_cart) — a
        # real coupon can still stack on top of it, same as two independent
        # discounts on the same subtotal.
        discount = cart.ready_build_discount or Decimal("0")
        applied_code: Optional[str] = None
        if code:
            try:
                from app.services.marketing.coupon_service import CouponCartLine

                lines = [
                    CouponCartLine(slug=line.slug, unit_price=line.unit_price, quantity=line.quantity)
                    for line in cart.items
                ]
                resolved = resolve_coupon_discount(self._db, code, subtotal, lines)
            except CouponError:
                resolved = None
            if resolved:
                discount += resolved.amount
                applied_code = resolved.code

        discount = min(discount, subtotal)

        taxable = max(subtotal - discount, Decimal("0"))
        # Nothing to ship — a digital-only order never carries a delivery charge.
        shipping = (
            Decimal("0")
            if self._cart_svc.is_digital_only_cart(cart)
            else resolve_shipping_amount(self._db, shipping_method, subtotal, district=district)
        )
        # Shipping is taxed only when the admin says so.
        if shipping_is_taxable(self._db):
            taxable += shipping
        tax = resolve_tax_amount(self._db, taxable)
        grand = max(max(subtotal - discount, Decimal("0")) + tax + shipping, Decimal("0"))
        return CheckoutTotals(
            subtotal=subtotal,
            discount=discount,
            tax=tax,
            shipping=shipping,
            grand_total=grand,
            coupon_code=applied_code,
        )

    def validate_for_checkout(
        self,
        cart: StorefrontCart,
        request: CheckoutPlaceRequest,
    ) -> List[str]:
        errors: List[str] = []

        if not cart.items:
            errors.append("Cart is empty")

        cart_issues = self._cart_svc.validate_cart(cart, sync_prices=True)
        blocking = [i for i in cart_issues if i.blocking]
        errors.extend(i.message for i in blocking)

        digital_only = bool(cart.items) and self._cart_svc.is_digital_only_cart(cart)
        errors.extend(self._validate_address(request.billing, prefix="Billing", require_address=not digital_only))
        errors.extend(self._validate_address(request.shipping, prefix="Shipping", require_address=not digital_only))

        if digital_only and request.payment_method.strip().lower() == "cod":
            errors.append(
                "Digital products require online payment — Cash on Delivery isn't available for this order."
            )

        if request.customer_id:
            customer = self._db.get(CommerceCustomer, request.customer_id)
            if not customer or customer.status != "active":
                errors.append("Customer account is not available")

        if not is_payment_method_allowed(self._db, request.payment_method):
            errors.append("Selected payment method is not available")

        if not is_shipping_method_allowed(self._db, request.shipping_method):
            errors.append("Selected shipping method is not available")
        elif request.shipping_method.strip().lower() == "express":
            # Next-business-day express delivery only covers Dhaka.
            place = (request.shipping.region or request.shipping.city or "").strip().lower()
            if place != "dhaka":
                errors.append("Express Delivery is available in Dhaka only")

        return errors

    def place_order(
        self,
        cart: StorefrontCart,
        request: CheckoutPlaceRequest,
        *,
        user: Optional[AuthUser] = None,
        storefront_customer: Optional[CommerceCustomer] = None,
        site_id: Optional[str] = None,
    ) -> CheckoutPlaceResult:
        errors = self.validate_for_checkout(cart, request)
        if errors:
            raise CheckoutError(errors[0])

        cart = self._cart_svc.load_cart(cart.id)
        district = (
            (request.shipping.region or request.shipping.city or "").strip()
        )
        totals = self.preview(
            cart,
            shipping_method=request.shipping_method,
            coupon_code=request.coupon_code,
            district=district,
        )

        customer = self._resolve_customer(request, user, storefront_customer=storefront_customer)
        warehouse_id = cart.warehouse_id or self._default_warehouse_id()
        now = datetime.utcnow()
        order_number = self._order_number()

        customer_name = compose_person_name(request.billing.first_name, request.billing.last_name)
        # Record the button the shopper actually pressed. A shop that renames
        # "Card / SSLCommerz" to "Bank Transfer" would otherwise file the order
        # under the gateway's own name, and staff taking the customer's call
        # would find no "Bank Transfer" anywhere. The gateway is still
        # recoverable from the pay:<id> tag below.
        payment_label = (
            payment_label_overrides(self._db).get(request.payment_method)
            or PAYMENT_LABELS.get(request.payment_method, request.payment_method)
        )

        timeline = [
            {
                "id": f"evt_{uuid.uuid4().hex[:8]}",
                "type": "created",
                "label": "Order placed",
                "at": now.isoformat(),
                "source": "storefront_checkout",
            },
        ]
        activities = [
            {
                "id": f"act_{uuid.uuid4().hex[:8]}",
                "type": "order_created",
                "message": f"Web order {order_number} placed",
                "at": now.isoformat(),
                "actor": (
                    (storefront_customer.email or storefront_customer.phone)
                    if storefront_customer
                    else (user.email if user else "storefront")
                ),
            },
        ]

        pickup_label = (
            pickup_point_label(self._db, request.pickup_point)
            if request.shipping_method == "pickup"
            else None
        )
        order = CommerceOrder(
            company_id=DEFAULT_COMPANY_ID,
            site_id=site_id,
            order_number=order_number,
            order_date=now,
            status="pending",
            payment_status="unpaid",
            shipment_status="unfulfilled",
            source="Web Store",
            customer_id=customer.id,
            customer_name=customer_name,
            customer_phone=request.billing.phone.strip(),
            customer_email=request.billing.email.strip().lower(),
            customer_group=customer.group,
            customer_order_count=customer.total_orders + 1,
            billing_address=request.billing.line1.strip(),
            billing_city=request.billing.city.strip() or None,
            billing_region=request.billing.region.strip() or request.billing.city.strip() or None,
            billing_country=request.billing.country,
            shipping_address=request.shipping.line1.strip(),
            shipping_city=request.shipping.city.strip() or None,
            shipping_region=request.shipping.region.strip() or request.shipping.city.strip() or None,
            shipping_country=request.shipping.country,
            payment_method=payment_label,
            paid_amount=Decimal("0"),
            due_amount=totals.grand_total,
            shipping_cost=totals.shipping,
            subtotal=totals.subtotal,
            discount_amount=totals.discount,
            tax_amount=totals.tax,
            shipping_amount=totals.shipping,
            grand_total=totals.grand_total,
            notes=self._compose_notes(
                request.notes,
                request.shipping_method,
                request.coupon_code,
                pickup_label,
            ),
            pickup_point=pickup_label,
            timeline_json=dump_json(timeline),
            activities_json=dump_json(activities),
            tags_json=dump_json(
                [
                    "storefront",
                    f"pay:{request.payment_method}",
                    f"ship:{request.shipping_method}",
                ],
            ),
        )
        self._db.add(order)
        self._db.flush()

        from app.services.commerce.commerce_order_service import CommerceOrderService

        order_svc = CommerceOrderService(self._db)
        billing_addr = order_svc.create_address_snapshot(
            order,
            address_type="billing",
            first_name=request.billing.first_name,
            last_name=request.billing.last_name,
            email=request.billing.email,
            phone=request.billing.phone,
            line1=request.billing.line1,
            city=request.billing.city,
            region=request.billing.region,
            postal_code=request.billing.postal_code,
            country=request.billing.country,
        )
        shipping_addr = order_svc.create_address_snapshot(
            order,
            address_type="shipping",
            first_name=request.shipping.first_name,
            last_name=request.shipping.last_name,
            email=request.shipping.email,
            phone=request.shipping.phone,
            line1=request.shipping.line1,
            city=request.shipping.city,
            region=request.shipping.region,
            postal_code=request.shipping.postal_code,
            country=request.shipping.country,
        )
        order.billing_address_id = billing_addr.id
        order.shipping_address_id = shipping_addr.id
        order.warehouse_id = warehouse_id

        commerce_items: list[CommerceOrderItem] = []
        for idx, line in enumerate(cart.items):
            line_total = line.unit_price * line.quantity
            item_row = CommerceOrderItem(
                order_id=order.id,
                product_id=line.product_id,
                item_id=line.item_id,
                variant_id=line.variant_id,
                sku=line.sku_snapshot or line.slug,
                name=line.name_snapshot,
                image_url=line.thumbnail,
                variant_label=line.variant_label,
                attributes_json=getattr(line, "attributes_json", None),
                quantity=line.quantity,
                unit_price=line.unit_price,
                tax_amount=line.tax_amount,
                line_total=line_total,
                sort_order=idx,
            )
            self._db.add(item_row)
            commerce_items.append(item_row)
            self._reserve_line(line, warehouse_id, order.id, order_number)

        self._db.flush()

        from app.services.sales.sales_service import SalesService

        SalesService(self._db).sync_from_storefront_order(
            order,
            commerce_items,
            warehouse_id=warehouse_id,
        )

        self._update_customer_after_order(customer, order, now)
        invoice = self._prepare_invoice(customer, order)
        prepared = get_payment_plugin(request.payment_method).prepare(order, totals.grand_total)
        payment_row = self._prepare_payment_record(order, customer, prepared)

        payment_timeline = load_json(order.payment_timeline_json, [])
        payment_timeline.append(
            {
                "id": f"pay_{uuid.uuid4().hex[:8]}",
                "status": prepared.status,
                "method": request.payment_method,
                "amount": str(prepared.amount),
                "at": now.isoformat(),
            },
        )
        order.payment_timeline_json = dump_json(payment_timeline)
        order.payment_id = payment_row.id
        order.invoice_id = invoice.id if invoice else None

        order_svc._record_event(
            order,
            event_type="order_created",
            actor=user.email if user else "guest",
            message=f"Storefront checkout {order_number}",
            to_status="pending",
            to_payment_status=order.payment_status,
            to_shipment_status=order.shipment_status,
            payload={
                "customer_id": customer.id,
                "payment_id": payment_row.id,
                "invoice_id": invoice.id if invoice else None,
                "billing_address_id": billing_addr.id,
                "shipping_address_id": shipping_addr.id,
            },
        )

        if totals.coupon_code:
            record_coupon_redemption(self._db, totals.coupon_code)

        self._cart_svc.clear_cart(cart)
        self._db.commit()

        return CheckoutPlaceResult(
            order=order,
            prepared_payment=prepared,
            invoice_id=invoice.id if invoice else None,
            payment_record_id=payment_row.id if payment_row else None,
        )

    def _validate_address(
        self,
        address: CheckoutAddress,
        *,
        prefix: str,
        require_address: bool = True,
    ) -> List[str]:
        errors: List[str] = []
        if not address.first_name.strip():
            errors.append(f"{prefix} first name is required")
        if not address.last_name.strip():
            errors.append(f"{prefix} last name is required")
        if not address.email.strip() or "@" not in address.email:
            errors.append(f"{prefix} email is invalid")
        if not address.phone.strip():
            errors.append(f"{prefix} phone is required")
        # A digital-only order has nothing to deliver, so street address / city
        # are never asked for and never required.
        if require_address:
            if not address.line1.strip():
                errors.append(f"{prefix} address is required")
            if not address.city.strip():
                errors.append(f"{prefix} city is required")
        return errors

    def _resolve_customer(
        self,
        request: CheckoutPlaceRequest,
        user: Optional[AuthUser],
        *,
        storefront_customer: Optional[CommerceCustomer] = None,
    ) -> CommerceCustomer:
        # Authenticated storefront session wins — never trust a foreign customer_id.
        if storefront_customer is not None:
            if storefront_customer.status != "active":
                raise CheckoutError("Customer account is not available")
            name = compose_person_name(request.billing.first_name, request.billing.last_name)
            if name:
                storefront_customer.name = name
            if request.billing.phone.strip():
                storefront_customer.phone = request.billing.phone.strip()
            if request.billing.email.strip():
                storefront_customer.email = request.billing.email.strip().lower()
            if request.billing.city.strip():
                storefront_customer.city = request.billing.city.strip()
            if request.billing.region.strip() or request.billing.city.strip():
                storefront_customer.region = (
                    request.billing.region.strip() or request.billing.city.strip()
                )
            if request.billing.country:
                storefront_customer.country = request.billing.country
            self._db.flush()
            return storefront_customer

        if request.customer_id:
            row = self._db.get(CommerceCustomer, request.customer_id)
            if row and row.status == "active":
                return row

        email = request.billing.email.strip().lower()
        existing = (
            self._db.query(CommerceCustomer)
            .filter(CommerceCustomer.email == email)
            .first()
        )
        if existing:
            return existing

        if user and user.party_id:
            by_party = (
                self._db.query(CommerceCustomer)
                .filter(CommerceCustomer.party_id == user.party_id)
                .first()
            )
            if by_party:
                return by_party

        name = compose_person_name(request.billing.first_name, request.billing.last_name)
        code = "CUST-" + "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(8))
        row = CommerceCustomer(
            id=str(uuid.uuid4()),
            company_id=DEFAULT_COMPANY_ID,
            customer_code=code,
            name=name,
            phone=request.billing.phone.strip(),
            email=email,
            city=request.billing.city.strip(),
            region=request.billing.region.strip() or request.billing.city.strip(),
            country=request.billing.country,
            customer_since=date.today(),
            status="active",
        )
        # party_id is NOT NULL in this schema — reuse the logged-in user's Party if there is one,
        # otherwise link/create a fresh Party for this guest checkout.
        if user and user.party_id:
            row.party_id = user.party_id
        else:
            from app.services.parties.commerce_party_bridge import ensure_party_for_customer

            ensure_party_for_customer(self._db, row)
        self._db.add(row)
        self._db.flush()
        return row

    def _update_customer_after_order(
        self,
        customer: CommerceCustomer,
        order: CommerceOrder,
        now: datetime,
    ) -> None:
        customer.total_orders += 1
        customer.total_spend += order.grand_total
        if customer.total_orders:
            customer.avg_order_value = customer.total_spend / customer.total_orders
        customer.last_order_date = now.date()

        timeline = load_json(customer.timeline_json, [])
        timeline.insert(
            0,
            {
                "id": f"tl_{uuid.uuid4().hex[:8]}",
                "type": "order",
                "label": f"Order {order.order_number}",
                "amount": str(order.grand_total),
                "at": now.isoformat(),
            },
        )
        customer.timeline_json = dump_json(timeline[:50])

        activities = load_json(customer.activities_json, [])
        activities.insert(
            0,
            {
                "id": f"ca_{uuid.uuid4().hex[:8]}",
                "type": "order_placed",
                "message": f"Placed order {order.order_number}",
                "at": now.isoformat(),
            },
        )
        customer.activities_json = dump_json(activities[:50])

        addresses = load_json(customer.addresses_json, [])
        shipping_snapshot = {
            "type": "shipping",
            "line1": order.shipping_address,
            "city": order.shipping_city,
            "region": order.shipping_region,
            "country": order.shipping_country,
        }
        if not any(a.get("line1") == shipping_snapshot["line1"] for a in addresses):
            addresses.append(shipping_snapshot)
            customer.addresses_json = dump_json(addresses[-10:])

        self._db.flush()

    def _reserve_line(
        self,
        line: StorefrontCartItem,
        warehouse_id: str,
        order_id: str,
        reference: str,
    ) -> None:
        if not line.item_id:
            raise CheckoutError(f"Missing item_id for {line.name_snapshot}")

        ec = self._cart_svc.resolve_ecommerce_item(item_id=line.item_id)
        snapshot = self._cart_svc.build_line_snapshot(
            ec,
            variant_id=line.variant_id,
            attributes=json.loads(line.attributes_json) if line.attributes_json else None,
            warehouse_id=warehouse_id,
        )

        if not snapshot.in_stock:
            raise CheckoutError(f"Stock unavailable for {line.name_snapshot}")

        if snapshot.product_id:
            self._consume_special_quota(snapshot.product_id, int(line.quantity))

        # Storefront uses catalog Manage Stock / Stock Status only — no warehouse.
        if not snapshot.track_quantity:
            return

        if line.quantity > snapshot.available_qty:
            raise CheckoutError(f"Stock unavailable for {line.name_snapshot}")

        from app.models.catalog_product import CatalogProduct

        product = self._db.get(CatalogProduct, snapshot.product_id)
        if product and product.track_quantity:
            next_stock = max(0, int(product.stock or 0) - int(line.quantity))
            product.stock = next_stock
            if product.product_type == "simple":
                from app.models.catalog_product_variant import CatalogProductVariant

                default = (
                    self._db.query(CatalogProductVariant)
                    .filter(
                        CatalogProductVariant.product_id == product.id,
                        CatalogProductVariant.is_default.is_(True),
                    )
                    .first()
                )
                if default:
                    default.stock = next_stock
            if snapshot.variant_id:
                from app.models.catalog_product_variant import CatalogProductVariant

                variant = self._db.get(CatalogProductVariant, snapshot.variant_id)
                if variant:
                    variant.stock = max(0, int(variant.stock or 0) - int(line.quantity))

    def _consume_special_quota(self, product_id: str, quantity: int) -> None:
        """The deal that was actually live for this product at checkout gets
        its quota debited — a limited-quantity special stops resolving as
        active once sold out, even mid-date-window (see resolve_active_special)."""
        from app.models.catalog_product_special import (
            CatalogProductSpecial,
            resolve_active_special,
        )

        specials = (
            self._db.query(CatalogProductSpecial)
            .filter(CatalogProductSpecial.product_id == product_id)
            .all()
        )
        active = resolve_active_special(specials)
        if active is None or active.quantity is None:
            return
        active.quantity_sold = int(active.quantity_sold or 0) + quantity
        if active.quantity_sold < active.quantity:
            return

        # Sold out — if this special is a Happy Hour / Offer campaign mirror,
        # disable the source deal too, so the admin's product list reflects it
        # (the row stays in the section; it just stops applying its price).
        if not (active.happy_hour_campaign_id or active.offer_campaign_id):
            return
        from app.models.catalog_product import CatalogProduct

        product = self._db.get(CatalogProduct, product_id)
        if not product:
            return
        if active.happy_hour_campaign_id:
            from app.routers.marketing_happy_hours import disable_happy_hour_deal_by_slug

            disable_happy_hour_deal_by_slug(self._db, active.happy_hour_campaign_id, product.slug)
        if active.offer_campaign_id:
            from app.routers.marketing_offers import disable_offer_deal_by_slug

            disable_offer_deal_by_slug(self._db, active.offer_campaign_id, product.slug)

    def _prepare_invoice(
        self,
        customer: CommerceCustomer,
        order: CommerceOrder,
    ) -> Optional[FinanceReceivable]:
        existing = (
            self._db.query(FinanceReceivable)
            .filter(
                FinanceReceivable.company_id == order.company_id,
                FinanceReceivable.source_type == "commerce_order",
                FinanceReceivable.source_id == order.id,
            )
            .first()
        )
        if existing:
            return existing

        receivable = FinanceReceivable(
            company_id=order.company_id,
            customer_id=customer.id,
            source_type="commerce_order",
            source_id=order.id,
            invoice_number=order.order_number,
            amount=order.grand_total,
            amount_paid=Decimal("0"),
            balance=order.grand_total,
            tax_amount=order.tax_amount,
            due_date=date.today(),
            status="open",
        )
        self._db.add(receivable)
        self._db.flush()
        return receivable

    def _prepare_payment_record(
        self,
        order: CommerceOrder,
        customer: CommerceCustomer,
        prepared: PreparedPayment,
    ) -> FinancePayment:
        payment_number = "PAY-" + "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(8))
        row = FinancePayment(
            company_id=order.company_id,
            payment_number=payment_number,
            payment_date=date.today(),
            amount=Decimal("0") if prepared.requires_action else prepared.amount,
            payment_method=prepared.payment_method,
            direction="inbound",
            source_type="commerce_order",
            source_id=order.id,
            party_type="customer",
            party_id=customer.id,
            reference=order.order_number,
            notes=json.dumps(
                {
                    "status": prepared.status,
                    "provider": prepared.provider,
                    "requires_action": prepared.requires_action,
                    "client_payload": prepared.client_payload,
                },
            ),
        )
        self._db.add(row)
        self._db.flush()
        return row

    def _default_warehouse_id(self) -> str:
        row = (
            self._db.query(InventoryWarehouse)
            .filter(
                InventoryWarehouse.company_id == DEFAULT_COMPANY_ID,
                InventoryWarehouse.is_active.is_(True),
            )
            .order_by(InventoryWarehouse.is_default.desc(), InventoryWarehouse.sort_order)
            .first()
        )
        if not row:
            raise CheckoutError("No active warehouse configured")
        return row.id

    def _order_number(self) -> str:
        return "ORD-" + "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(8))  # letters/digits only (no - or _), no look-alike 0/O/1/I

    @staticmethod
    def _compose_notes(
        notes: Optional[str],
        shipping_method: str,
        coupon_code: Optional[str],
        pickup_point: Optional[str] = None,
    ) -> Optional[str]:
        parts = []
        if notes and notes.strip():
            parts.append(notes.strip())
        parts.append(f"Shipping: {shipping_method}")
        # A pickup order is paid like any other, so the counter is the only thing
        # telling staff where to hand the goods over.
        if shipping_method == "pickup" and (pickup_point or "").strip():
            parts.append(f"Pickup point: {pickup_point.strip()}")
        if coupon_code:
            parts.append(f"Coupon: {coupon_code}")
        return " · ".join(parts) if parts else None

    @staticmethod
    def address_from_legacy_payload(payload: dict[str, Any]) -> tuple[CheckoutAddress, CheckoutAddress, bool]:
        """Map flat STEP 04 payload to billing/shipping addresses."""
        billing_same = payload.get("billing_same_as_shipping", True)
        base = CheckoutAddress(
            first_name=payload["first_name"],
            last_name=payload["last_name"],
            email=payload["email"],
            phone=payload["phone"],
            line1=payload.get("billing_address") or payload["address"],
            city=payload.get("billing_city") or payload.get("district", ""),
            region=payload.get("billing_region") or payload.get("district", ""),
            postal_code=payload.get("billing_postal_code") or payload.get("postal_code", ""),
            country=payload.get("billing_country", "Bangladesh"),
        )
        if billing_same:
            return base, base, True
        shipping = CheckoutAddress(
            first_name=payload.get("shipping_first_name") or payload["first_name"],
            last_name=payload.get("shipping_last_name") or payload["last_name"],
            email=payload["email"],
            phone=payload.get("shipping_phone") or payload["phone"],
            line1=payload.get("shipping_address") or payload["address"],
            city=payload.get("shipping_city") or payload.get("district", ""),
            region=payload.get("shipping_region") or payload.get("district", ""),
            postal_code=payload.get("shipping_postal_code") or payload.get("postal_code", ""),
            country=payload.get("shipping_country", "Bangladesh"),
        )
        return base, shipping, False
