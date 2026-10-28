"""Resolve storefront shipping methods from Business Settings (platform_settings).

Rules:
- Method toggles gate which options appear on checkout.
- Home Delivery (standard) uses per-district rates from `shipping.district_rates`.
- Express / Same Day use flat rates from settings.
- Pickup is always free when enabled.
- Free shipping only when `shipping.free_threshold` > 0 and subtotal meets it.
"""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.platform_setting import PlatformSetting
from app.services.ecommerce.bd_locations import BD_DISTRICTS, DEFAULT_SUB_DISTRICTS

# All 64 districts. Dhaka has its own rate; every other district is charged
# shipping.rate_default (120).
DEFAULT_ZONES = list(BD_DISTRICTS)

DEFAULT_DISTRICT_RATES: Dict[str, str] = {
    "Dhaka": "60",
}

DEFAULT_PICKUP_POINTS: List[Dict[str, str]] = [
    {
        "key": "idb-branch",
        "label": "IDB Branch",
        "address": "Shop# 315 (3rd Floor), BCS Computer City,\nIDB Bhaban, Agargaon, Dhaka-1207",
        "phone": "01913-004278",
        "map_url": "",
    },
    {
        "key": "multiplan-branch",
        "label": "Multiplan Branch",
        "address": "Shop# 650/A (Level-06),\nNew Elephant Road, Dhaka-1205",
        "phone": "01913-004278",
        "map_url": "",
    },
    {
        "key": "mirpur-branch",
        "label": "Mirpur Branch",
        "address": "Shop# 67 (5th Floor), Shah Ali Plaza,\nMirpur 10, Dhaka-1216",
        "phone": "01913-004278",
        "map_url": "",
    },
]

SHIPPING_SETTING_DEFAULTS: Dict[str, str] = {
    # 0 = disabled (no auto free shipping)
    "shipping.free_threshold": "0",
    "shipping.default_method": "standard",
    "shipping.time_slots": "true",
    "shipping.method_standard": "true",
    "shipping.method_express": "true",
    "shipping.method_same_day": "false",
    "shipping.method_pickup": "true",
    "shipping.rate_default": "120",
    "shipping.rate_express": "150",
    "shipping.rate_same_day": "200",
    "shipping.zones": ",".join(DEFAULT_ZONES),
    "shipping.district_rates": json.dumps(DEFAULT_DISTRICT_RATES, ensure_ascii=False),
    "shipping.pickup_points": json.dumps(DEFAULT_PICKUP_POINTS, ensure_ascii=False),
    # Only the districts an admin has edited; the rest fall back to the built-in
    # list, so this stays small instead of copying all 64 districts.
    "shipping.sub_districts": "{}",
}


def _truthy(raw: Optional[str], default: bool) -> bool:
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _decimal(raw: Optional[str], default: Decimal) -> Decimal:
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return Decimal(str(raw).strip())
    except (InvalidOperation, ValueError):
        return default


def _split_list(raw: Optional[str], fallback: List[str]) -> List[str]:
    if raw is None or not str(raw).strip():
        return list(fallback)
    parts = [p.strip() for p in str(raw).replace("\n", ",").split(",")]
    out = [p for p in parts if p]
    return out or list(fallback)


def parse_district_rates(raw: Optional[str]) -> Dict[str, Decimal]:
    """Parse JSON object or `District:amount` / `District=amount` lines/CSV."""
    text = (raw or "").strip()
    out: Dict[str, Decimal] = {}
    if not text:
        for name, val in DEFAULT_DISTRICT_RATES.items():
            out[name] = _decimal(val, Decimal("120"))
        return out

    if text.startswith("{"):
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                for k, v in data.items():
                    name = str(k).strip()
                    if not name:
                        continue
                    out[name] = _decimal(str(v), Decimal("0"))
                if out:
                    return out
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    for part in text.replace("\n", ",").split(","):
        chunk = part.strip()
        if not chunk:
            continue
        if ":" in chunk:
            name, amount = chunk.split(":", 1)
        elif "=" in chunk:
            name, amount = chunk.split("=", 1)
        else:
            continue
        name = name.strip()
        if not name:
            continue
        out[name] = _decimal(amount.strip(), Decimal("0"))

    if not out:
        for name, val in DEFAULT_DISTRICT_RATES.items():
            out[name] = _decimal(val, Decimal("120"))
    return out


def parse_pickup_points(raw: Optional[str]) -> List[Dict[str, str]]:
    """Read the admin-managed collection counters.

    Anything unreadable falls back to the built-in pair rather than an empty
    list — a customer who picked Pickup must always be told where to go.
    """
    text = (raw or "").strip()
    if not text:
        return [dict(p) for p in DEFAULT_PICKUP_POINTS]
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError, ValueError):
        return [dict(p) for p in DEFAULT_PICKUP_POINTS]
    if not isinstance(data, list):
        return [dict(p) for p in DEFAULT_PICKUP_POINTS]

    out: List[Dict[str, str]] = []
    for index, entry in enumerate(data):
        if not isinstance(entry, dict):
            continue
        label = str(entry.get("label") or "").strip()
        if not label:
            continue
        key = str(entry.get("key") or "").strip() or f"point-{index + 1}"
        out.append(
            {
                "key": key,
                "label": label,
                "address": str(entry.get("address") or "").strip(),
                "phone": str(entry.get("phone") or "").strip(),
                "map_url": str(entry.get("map_url") or "").strip(),
            }
        )
    return out or [dict(p) for p in DEFAULT_PICKUP_POINTS]


def _sub_district_overrides(raw: Optional[str]) -> Dict[str, List[str]]:
    text = (raw or "").strip()
    if not text or not text.startswith("{"):
        return {}
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}

    out: Dict[str, List[str]] = {}
    for district, names in data.items():
        key = str(district).strip()
        if not key:
            continue
        if isinstance(names, str):
            names = names.replace("\n", ",").split(",")
        if not isinstance(names, list):
            continue
        cleaned = [str(n).strip() for n in names]
        out[key] = [n for n in cleaned if n]
    return out


# Districts renamed since the built-in list was compiled; a shop that uses the
# current spelling must still find its sub-districts.
DISTRICT_ALIASES: Dict[str, str] = {
    "chattogram": "Chittagong",
    "barishal": "Barisal",
    "bogra": "Bogura",
    "jessore": "Jashore",
    "comilla": "Cumilla",
    "cumilla": "Comilla",
    "jashore": "Jessore",
    "barisal": "Barishal",
    "chittagong": "Chattogram",
}


def sub_districts_for(
    districts: List[str],
    overrides: Dict[str, List[str]],
) -> Dict[str, List[str]]:
    """Sub-districts to offer for each checkout district.

    An admin edit wins; otherwise the built-in list is matched case-insensitively
    so a district typed as "dhaka" still finds its upazilas. A district nobody
    recognises gets itself, so the customer is never left with an empty list.
    """
    by_lower = {name.lower(): names for name, names in DEFAULT_SUB_DISTRICTS.items()}
    override_by_lower = {name.lower(): names for name, names in overrides.items()}

    out: Dict[str, List[str]] = {}
    for district in districts:
        name = (district or "").strip()
        if not name:
            continue
        lower = name.lower()
        chosen = override_by_lower.get(lower)
        if chosen is None:
            chosen = by_lower.get(lower)
        if chosen is None:
            alias = DISTRICT_ALIASES.get(lower)
            if alias:
                chosen = by_lower.get(alias.lower())
        out[name] = list(chosen) if chosen else [name]
    return out


def load_shipping_settings(db: Session) -> Dict[str, str]:
    keys = list(SHIPPING_SETTING_DEFAULTS.keys())
    # Also read legacy keys so older installs keep working until re-saved
    legacy = ("shipping.rate_inside", "shipping.rate_outside", "shipping.inside_zones")
    rows = (
        db.query(PlatformSetting)
        .filter(PlatformSetting.key.in_([*keys, *legacy]))
        .all()
    )
    by_key = {r.key: (r.value if r.value is not None else "") for r in rows}
    out = {
        key: (by_key[key] if key in by_key and str(by_key[key]).strip() != "" else default)
        for key, default in SHIPPING_SETTING_DEFAULTS.items()
    }

    # Migrate empty district_rates from legacy inside/outside if needed
    if (
        key_empty(by_key.get("shipping.district_rates"))
        and not key_empty(by_key.get("shipping.rate_inside"))
    ):
        inside = _decimal(by_key.get("shipping.rate_inside"), Decimal("60"))
        outside = _decimal(by_key.get("shipping.rate_outside"), Decimal("120"))
        inside_zones = {
            z.strip().lower()
            for z in _split_list(by_key.get("shipping.inside_zones"), ["Dhaka"])
        }
        zones = _split_list(out.get("shipping.zones"), DEFAULT_ZONES)
        migrated = {
            z: str(inside if z.strip().lower() in inside_zones else outside) for z in zones
        }
        out["shipping.district_rates"] = json.dumps(migrated, ensure_ascii=False)
        out["shipping.rate_default"] = str(outside)

    return out


def key_empty(raw: Optional[str]) -> bool:
    return raw is None or str(raw).strip() == ""


def district_rate_for(
    district: str,
    rates: Dict[str, Decimal],
    default: Decimal,
) -> Decimal:
    d = (district or "").strip().lower()
    if not d:
        # Prefer Dhaka if present, else default
        for name, amount in rates.items():
            if name.strip().lower() == "dhaka":
                return amount
        return default
    for name, amount in rates.items():
        if name.strip().lower() == d:
            return amount
    return default


def list_available_shipping_options(db: Session) -> List[dict[str, Any]]:
    s = load_shipping_settings(db)
    rates = parse_district_rates(s.get("shipping.district_rates"))
    rate_default = _decimal(s.get("shipping.rate_default"), Decimal("120"))
    rate_express = _decimal(s.get("shipping.rate_express"), Decimal("150"))
    rate_same_day = _decimal(s.get("shipping.rate_same_day"), Decimal("200"))
    free_threshold = _decimal(s.get("shipping.free_threshold"), Decimal("0"))
    dhaka_rate = district_rate_for("Dhaka", rates, rate_default)

    district_rates_payload = {name: str(amount) for name, amount in rates.items()}

    out: List[dict[str, Any]] = []

    if _truthy(s.get("shipping.method_standard"), True):
        out.append(
            {
                "id": "standard",
                "label": "Home Delivery",
                "eta": "2–4 business days",
                "base_price": str(dhaka_rate),
                "free_over_threshold": free_threshold > 0,
                "pricing": "district",
                "rate_default": str(rate_default),
                "district_rates": district_rates_payload,
            }
        )

    if _truthy(s.get("shipping.method_express"), True):
        out.append(
            {
                "id": "express",
                "label": "Express Delivery",
                "eta": "Next business day",
                "base_price": str(rate_express),
                "free_over_threshold": False,
                "pricing": "flat",
                "rate_default": str(rate_express),
                "district_rates": {},
            }
        )

    if _truthy(s.get("shipping.method_same_day"), False):
        out.append(
            {
                "id": "same_day",
                "label": "Same Day Delivery",
                "eta": "Same day (eligible areas)",
                "base_price": str(rate_same_day),
                "free_over_threshold": False,
                "pricing": "flat",
                "rate_default": str(rate_same_day),
                "district_rates": {},
            }
        )

    if _truthy(s.get("shipping.method_pickup"), True):
        out.append(
            {
                "id": "pickup",
                "label": "Store Pickup",
                "eta": "Ready for pickup",
                "base_price": "0",
                "free_over_threshold": False,
                "pricing": "free",
                "rate_default": "0",
                "district_rates": {},
            }
        )

    for m in out:
        m["free_threshold"] = str(free_threshold)

    return out


def shipping_label_overrides(db: Session) -> Dict[str, str]:
    """Shop-chosen wording for the delivery buttons, keyed by method id.

    Built-in names like "Store Pickup" suit most shops, but the wording belongs
    to the shop — so it is a setting rather than a release.
    """
    rows = (
        db.query(PlatformSetting)
        .filter(PlatformSetting.key.like("shipping.%.label"))
        .all()
    )
    out: Dict[str, str] = {}
    for row in rows:
        parts = row.key.split(".")
        if len(parts) == 3 and str(row.value or "").strip():
            out[parts[1]] = str(row.value).strip()
    return out


def shipping_options_payload(db: Session) -> dict[str, Any]:
    s = load_shipping_settings(db)
    zones = _split_list(s.get("shipping.zones"), DEFAULT_ZONES)
    rates = parse_district_rates(s.get("shipping.district_rates"))
    # Ensure every zone has a rate entry for the admin/checkout UI
    rate_default = _decimal(s.get("shipping.rate_default"), Decimal("120"))
    for z in zones:
        if z not in rates and not any(z.lower() == k.lower() for k in rates):
            rates[z] = rate_default

    default_method = (s.get("shipping.default_method") or "standard").strip() or "standard"
    methods = list_available_shipping_options(db)
    label_overrides = shipping_label_overrides(db)
    # Refresh district_rates on standard method with completed map
    for m in methods:
        if m.get("pricing") == "district":
            m["district_rates"] = {name: str(amount) for name, amount in rates.items()}
        override = label_overrides.get(str(m.get("id") or ""))
        if override:
            m["label"] = override

    allowed_ids = {m["id"] for m in methods}
    if default_method not in allowed_ids and methods:
        default_method = methods[0]["id"]

    return {
        "shipping_methods": methods,
        "zones": zones,
        "district_rates": {name: str(amount) for name, amount in rates.items()},
        "free_threshold": str(_decimal(s.get("shipping.free_threshold"), Decimal("0"))),
        "default_method": default_method,
        "time_slots_enabled": _truthy(s.get("shipping.time_slots"), True),
        "pickup_points": parse_pickup_points(s.get("shipping.pickup_points")),
        "sub_districts": sub_districts_for(
            zones,
            _sub_district_overrides(s.get("shipping.sub_districts")),
        ),
    }


def is_shipping_method_allowed(db: Session, method_id: str) -> bool:
    return method_id in {m["id"] for m in list_available_shipping_options(db)}


def resolve_shipping_amount(
    db: Session,
    method_id: str,
    subtotal: Decimal,
    *,
    district: str = "",
) -> Decimal:
    s = load_shipping_settings(db)
    methods = {m["id"]: m for m in list_available_shipping_options(db)}
    method = methods.get(method_id) or methods.get("standard")
    if not method:
        return Decimal("0")

    pricing = method.get("pricing") or "flat"
    if pricing == "free" or method["id"] == "pickup":
        return Decimal("0")

    free_threshold = _decimal(s.get("shipping.free_threshold"), Decimal("0"))
    free_over = bool(method.get("free_over_threshold"))
    if free_over and free_threshold > 0 and subtotal >= free_threshold:
        return Decimal("0")

    if pricing == "district":
        rates = parse_district_rates(s.get("shipping.district_rates"))
        # Also accept rates embedded on method (from options builder)
        embedded = method.get("district_rates") or {}
        if isinstance(embedded, dict) and embedded:
            for k, v in embedded.items():
                rates[str(k)] = _decimal(str(v), rates.get(str(k), Decimal("0")))
        default = _decimal(
            str(method.get("rate_default") or s.get("shipping.rate_default")),
            Decimal("120"),
        )
        return district_rate_for(district, rates, default)

    # legacy zone pricing (if any stale client still sends)
    if pricing == "zone":
        rates = parse_district_rates(s.get("shipping.district_rates"))
        default = _decimal(s.get("shipping.rate_default"), Decimal("120"))
        return district_rate_for(district, rates, default)

    return _decimal(str(method.get("base_price")), Decimal("0"))
