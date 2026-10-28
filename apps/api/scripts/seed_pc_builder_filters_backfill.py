"""Real values for the Stage-A Filters Registry fields that Stage B's new
condition-based slot matching now requires — without this, a slot whose
condition references a brand-new field (e.g. Storage's storage_interface)
would show zero products until an admin manually fills it in per product.
This backfills real seeded PC-Builder products only, the same small known
set seed_pc_builder_parts.py already covers, plus the two real motherboards
and one real cooler discovered missing chipset/socket_support values when
the new condition-based slot matching went live.

Idempotent — matches by real catalog_product_id/attribute code, safe to
re-run.

Usage (API container):
    python scripts/seed_pc_builder_filters_backfill.py
"""

from __future__ import annotations

import uuid

from app.database import SessionLocal
from app.models.catalog_attribute import CatalogAttribute
from app.models.catalog_product import CatalogProduct  # noqa: F401 — registers the FK target
from app.models.catalog_product_attribute_value import CatalogProductAttributeValue

# product_id, attribute_code, value
VALUES: list[tuple[str, str, str]] = [
    # Motherboards missing chipset (had socket/ram_type only from Phase 1)
    ("86332837-cab9-4976-bb52-db303c31bee2", "chipset", "B760"),  # ASUS PRIME B760M-A WiFi
    ("de94e94d-ddef-4d78-a500-ad0d98cef193", "chipset", "B550"),  # MSI PRO B550M-VC WiFi
    # CPU Cooler missing socket_support (Phase 1 left this one bare)
    ("df3cd639-fddc-4390-ac83-e8c30463a689", "socket_support", "AM4,AM5,LGA1700,LGA1200"),
    ("df3cd639-fddc-4390-ac83-e8c30463a689", "cooler_type", "AIO"),
    ("df3cd639-fddc-4390-ac83-e8c30463a689", "cooler_radiator_size", "240"),
    # Storage — new field, never populated
    ("3da0f446-1df4-4d7d-8c86-c72724ebfcec", "storage_interface", "M.2 NVMe"),  # Kingston NV2
    ("c3148f10-dcfe-4906-b009-8c42958685a7", "storage_interface", "M.2 NVMe"),  # Samsung 990 Pro
    # Graphics Card — new field, never populated
    ("28dd64b6-9895-42ba-b462-9e4214d3b405", "gpu_chipset", "RTX 4070"),
    ("28dd64b6-9895-42ba-b462-9e4214d3b405", "gpu_length", "227"),
    ("28dd64b6-9895-42ba-b462-9e4214d3b405", "gpu_recommended_psu", "650"),
    ("96935264-0185-4471-ab79-494a559b7c12", "gpu_chipset", "RTX 4060"),
    ("96935264-0185-4471-ab79-494a559b7c12", "gpu_length", "200"),
    ("96935264-0185-4471-ab79-494a559b7c12", "gpu_recommended_psu", "550"),
    # Casing — new field, never populated
    ("8bd3636b-7611-4174-abed-f75fb39cbe12", "case_motherboard_support", "ATX,Micro-ATX,Mini-ITX"),
    ("8bd3636b-7611-4174-abed-f75fb39cbe12", "case_max_gpu_length", "330"),
    ("307f81cd-e197-4f2c-84ec-3efe9f8b15d5", "case_motherboard_support", "Micro-ATX,Mini-ITX"),
    ("307f81cd-e197-4f2c-84ec-3efe9f8b15d5", "case_max_gpu_length", "300"),
    ("0b360e94-a236-4ef7-8398-2ca38985aca2", "case_motherboard_support", "ATX,Micro-ATX,Mini-ITX"),
    ("0b360e94-a236-4ef7-8398-2ca38985aca2", "case_max_gpu_length", "365"),
]


def main() -> None:
    db = SessionLocal()
    try:
        attrs = {a.code: a for a in db.query(CatalogAttribute).all()}
        written = 0
        for product_id, code, value in VALUES:
            attr = attrs.get(code)
            if not attr:
                print(f"  skip {code}: attribute not found")
                continue
            row = (
                db.query(CatalogProductAttributeValue)
                .filter(
                    CatalogProductAttributeValue.product_id == product_id,
                    CatalogProductAttributeValue.attribute_id == attr.id,
                )
                .first()
            )
            if row:
                if row.value != value:
                    row.value = value
                    written += 1
            else:
                db.add(
                    CatalogProductAttributeValue(
                        id=str(uuid.uuid4()),
                        product_id=product_id,
                        attribute_id=attr.id,
                        value=value,
                    )
                )
                written += 1
        db.commit()
        print(f"Done. wrote/updated {written} values.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
