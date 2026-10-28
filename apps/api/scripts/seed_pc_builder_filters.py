"""Filters Registry foundation (Phase 4, Stage A).

The Configurator's Rules/Slots/Test-Build admin surfaces need to know each
attribute's real TYPE (number/boolean/multi_select/dropdown/text) to narrow
operators and drive a condition-builder the way the reference artifact's
FILTERS registry does. `CatalogAttribute.field_type` already exists as a
column but the write path so far only ever set "text" — this script widens
it to the real type per field, and reorganizes the flat "PC Builder
Compatibility" group into one group per component (CPU/Motherboard/Memory/
Graphics Card/Power Supply/Casing/CPU Cooler/Storage/Monitor) so a slot's
condition-builder can show only the fields relevant to that slot's profile.

Existing attribute codes (socket, ram_type, tdp, wattage, socket_support,
chipset, generation) are NEVER renamed — every rule, alias, override, and
resolver in this codebase already references them by code. This script only
retypes/regroups them and adds the new codes the artifact's real rule set
needs (igpu, form factors, slot counts, lengths, etc.) that don't exist yet.

Idempotent — safe to re-run; matches by profile/group/attribute code and
updates in place rather than duplicating, so existing product attribute
values (keyed by attribute_id) are never orphaned.

Usage (API container):
    python scripts/seed_pc_builder_filters.py
"""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.catalog_attribute import CatalogAttribute
from app.models.catalog_attribute_group import CatalogAttributeGroup
from app.models.catalog_attribute_profile import CatalogAttributeProfile

PROFILE_CODE = "pc_builder_specs"

# group_code, group_name, sort_order
GROUPS: list[tuple[str, str, int]] = [
    ("cpu", "CPU", 1),
    ("motherboard", "Motherboard", 2),
    ("memory", "Memory", 3),
    ("graphics_card", "Graphics Card", 4),
    ("power_supply", "Power Supply", 5),
    ("casing", "Casing", 6),
    ("cpu_cooler", "CPU Cooler", 7),
    ("storage", "Storage", 8),
    ("monitor", "Monitor", 9),
]

# group_code, code, name, field_type, unit, predefined_values (comma list or None)
FIELD_TYPE_MULTI = "multi_select"
FIELD_TYPE_NUM = "number"
FIELD_TYPE_BOOL = "boolean"
FIELD_TYPE_SELECT = "dropdown"
FIELD_TYPE_TEXT = "text"

FIELDS: list[tuple[str, str, str, str, Optional[str]]] = [
    # --- CPU (socket/generation/tdp already exist — retype+regroup only) ---
    ("cpu", "socket", "Socket", FIELD_TYPE_SELECT, None),
    ("cpu", "generation", "Generation", FIELD_TYPE_SELECT, None),
    ("cpu", "tdp", "TDP", FIELD_TYPE_NUM, "W"),
    ("cpu", "igpu", "Integrated Graphics", FIELD_TYPE_BOOL, None),
    # --- Motherboard (chipset/ram_type already exist) ---
    ("motherboard", "chipset", "Chipset", FIELD_TYPE_SELECT, None),
    ("motherboard", "ram_type", "Memory Type", FIELD_TYPE_SELECT, None),
    ("motherboard", "mb_form_factor", "Motherboard Form Factor", FIELD_TYPE_MULTI, None),
    ("motherboard", "ram_slots", "Memory Slots", FIELD_TYPE_NUM, None),
    ("motherboard", "max_ram", "Max Memory", FIELD_TYPE_NUM, "GB"),
    ("motherboard", "m2_slots", "M.2 Slots", FIELD_TYPE_NUM, None),
    ("motherboard", "sata_ports", "SATA Ports", FIELD_TYPE_NUM, None),
    # --- Memory ---
    ("memory", "type", "Type", FIELD_TYPE_SELECT, None),
    ("memory", "ram_capacity", "RAM Capacity", FIELD_TYPE_NUM, "GB"),
    ("memory", "ram_modules", "RAM Modules", FIELD_TYPE_NUM, None),
    ("memory", "ram_form_factor", "RAM Form Factor", FIELD_TYPE_MULTI, None),
    # --- Graphics Card ---
    ("graphics_card", "gpu_chipset", "GPU Chipset", FIELD_TYPE_SELECT, None),
    ("graphics_card", "gpu_length", "GPU Length", FIELD_TYPE_NUM, "mm"),
    ("graphics_card", "gpu_tdp", "GPU TDP", FIELD_TYPE_NUM, "W"),
    ("graphics_card", "gpu_recommended_psu", "Recommended PSU", FIELD_TYPE_NUM, "W"),
    ("graphics_card", "gpu_ports", "Ports", FIELD_TYPE_MULTI, None),
    # --- Power Supply (wattage already exists) ---
    ("power_supply", "wattage", "Wattage", FIELD_TYPE_NUM, "W"),
    ("power_supply", "psu_form_factor", "PSU Form Factor", FIELD_TYPE_MULTI, None),
    # --- Casing ---
    ("casing", "case_motherboard_support", "Motherboard Support", FIELD_TYPE_MULTI, None),
    ("casing", "case_max_gpu_length", "Max GPU Length", FIELD_TYPE_NUM, "mm"),
    ("casing", "case_max_cooler_height", "Max Cooler Height", FIELD_TYPE_NUM, "mm"),
    ("casing", "case_max_radiator", "Max Radiator", FIELD_TYPE_NUM, "mm"),
    ("casing", "case_psu_support", "PSU Support", FIELD_TYPE_MULTI, None),
    # --- CPU Cooler (socket_support already exists) ---
    ("cpu_cooler", "socket_support", "Cooler Socket Support", FIELD_TYPE_MULTI, None),
    ("cpu_cooler", "cooler_type", "Cooler Type", FIELD_TYPE_SELECT, None),
    ("cpu_cooler", "cooler_height", "Height", FIELD_TYPE_NUM, "mm"),
    ("cpu_cooler", "cooler_radiator_size", "Radiator Size", FIELD_TYPE_NUM, "mm"),
    ("cpu_cooler", "cooler_tdp_rating", "Cooler TDP Rating", FIELD_TYPE_NUM, "W"),
    # --- Storage ---
    ("storage", "storage_interface", "Storage Interface", FIELD_TYPE_SELECT, None),
    # --- Monitor ---
    ("monitor", "monitor_ports", "Ports", FIELD_TYPE_MULTI, None),
    ("monitor", "screen_size", "Screen Size", FIELD_TYPE_NUM, "inch"),
]


def ensure_profile(db: Session) -> CatalogAttributeProfile:
    profile = db.query(CatalogAttributeProfile).filter(CatalogAttributeProfile.code == PROFILE_CODE).first()
    if profile is None:
        profile = CatalogAttributeProfile(
            id=str(uuid.uuid4()),
            name="PC Builder Specs",
            code=PROFILE_CODE,
            description="Compatibility fields the Smart PC Builder rule engine reads.",
            is_active=True,
        )
        db.add(profile)
        db.flush()
        print("  created attribute profile pc_builder_specs")
    return profile


def ensure_groups(db: Session, profile: CatalogAttributeProfile) -> dict[str, CatalogAttributeGroup]:
    by_code: dict[str, CatalogAttributeGroup] = {}
    for code, name, sort_order in GROUPS:
        row = db.query(CatalogAttributeGroup).filter(CatalogAttributeGroup.code == code).first()
        if row is None:
            row = CatalogAttributeGroup(
                id=str(uuid.uuid4()),
                profile_id=profile.id,
                name=name,
                code=code,
                sort_order=sort_order,
                is_active=True,
            )
            db.add(row)
            db.flush()
            print(f"  created attribute group {code}")
        elif row.profile_id != profile.id:
            # After scripts/split_pc_builder_profiles.py each group lives in its own component
            # profile — don't pull it back into the old shared one.
            moved_out = db.get(CatalogAttributeProfile, row.profile_id)
            if moved_out is None or moved_out.code == PROFILE_CODE:
                row.profile_id = profile.id
        by_code[code] = row
    return by_code


def ensure_fields(db: Session, groups: dict[str, CatalogAttributeGroup]) -> None:
    our_group_ids = [g.id for g in groups.values()]
    # The original Phase-1 seed put everything in one flat "pc_builder"
    # group — include it in the search scope so those 7 existing attributes
    # (and their product values) get moved into their new per-component
    # group instead of being duplicated.
    old_group = db.query(CatalogAttributeGroup).filter(CatalogAttributeGroup.code == "pc_builder").first()
    if old_group:
        our_group_ids.append(old_group.id)
    for i, (group_code, code, name, field_type, unit) in enumerate(FIELDS):
        group = groups[group_code]
        row = db.query(CatalogAttribute).filter(CatalogAttribute.code == code, CatalogAttribute.group_id == group.id).first()
        if row is None:
            # A field with this code might exist under the OLD flat
            # "PC Builder Compatibility" group — move it here instead of
            # creating a duplicate, so any product values keyed by its
            # attribute_id stay valid. Scoped to OUR profile's groups only,
            # so an unrelated catalog attribute reusing the same code
            # elsewhere is never touched.
            row = (
                db.query(CatalogAttribute)
                .filter(CatalogAttribute.code == code, CatalogAttribute.group_id.in_(our_group_ids))
                .first()
            )
        if row is None:
            row = CatalogAttribute(
                id=str(uuid.uuid4()),
                group_id=group.id,
                name=name,
                code=code,
                field_type=field_type,
                sort_order=i,
                is_filterable=False,
                is_comparable=True,
                is_visible=True,
                is_active=True,
                storefront_filter_visible=False,
                unit=unit,
            )
            db.add(row)
            print(f"  created attribute {code} ({field_type}) in {group_code}")
        else:
            changed = False
            if row.group_id != group.id:
                row.group_id = group.id
                changed = True
            if row.field_type != field_type:
                row.field_type = field_type
                changed = True
            if row.unit != unit:
                row.unit = unit
                changed = True
            if row.name != name:
                row.name = name
                changed = True
            if changed:
                print(f"  updated attribute {code} -> type={field_type} group={group_code}")


def main() -> None:
    db = SessionLocal()
    try:
        print("Ensuring PC Builder Specs profile/groups/fields…")
        profile = ensure_profile(db)
        groups = ensure_groups(db, profile)
        ensure_fields(db, groups)
        db.commit()
        print("Done.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
