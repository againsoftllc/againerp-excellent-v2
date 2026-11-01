"""Rebuild an attribute profile in Star Tech's own shape.

    python restructure_profile.py "<profile name>" "<a Star Tech product page of that kind>"            -> dry run (everything runs, then is rolled back)
    python restructure_profile.py "<profile name>" "<url>" --apply

The groups and attributes become the ones of that product page's specification table (same names, same order); the category page's filters sit
inside them: same name -> the attribute keeps it, different name -> the attribute takes the FILTER's name. Every product's existing values are
mapped into the new attributes by meaning (the filter option as the value, the old wording as the text the product page shows); what has no
attribute any more stays on that product as its own extra spec - nothing is dropped.
"""
import json, re, sys
import main  # noqa: F401  (loads every model / router like the running server)
from app.database import SessionLocal
from app.models.catalog_attribute import CatalogAttribute
from app.models.catalog_attribute_group import CatalogAttributeGroup
from app.models.catalog_attribute_profile import CatalogAttributeProfile
from app.models.catalog_filter import CatalogFilter
from app.models.catalog_product import CatalogProduct
from app.models.catalog_product_attribute_value import CatalogProductAttributeValue as V
from app.routers.catalog_attribute_profiles import _replace_profile_structure, _sync_catalog_filters_for_profile
from app.schemas.attribute_profile import AttributeProfileBulkSaveRequest, BulkAttributeGroupItem, BulkAttributeItem
from app.services.catalog_ai import spec_profile_service as sp
from app.services.catalog_ai.scraper import fetch_page, fetch_trail_filters, merge_filters

NAME = sys.argv[1]
URLS = [a for a in sys.argv[2:] if a.startswith("http")]  # one or more Star Tech product pages of that kind: their spec tables are merged
URL = " + ".join(u.rsplit("/", 1)[-1] for u in URLS)
APPLY = "--apply" in sys.argv
VERBOSE = "--verbose" in sys.argv
OLD = "~old "
norm = sp._norm
db = SessionLocal()
prof = db.query(CatalogAttributeProfile).filter(CatalogAttributeProfile.name == NAME).first()
if prof is None:
    sys.exit("no profile named " + NAME)
company = prof.company_id

# ---- 1. the Star Tech shape
ref: list = []  # the pages' spec tables merged: groups by name in first-seen order, rows by label in first-seen order
filter_lists: list = []
for u in URLS:
    pg = fetch_page(u)
    for g in pg.spec_groups:
        tgt = next((x for x in ref if norm(x["group"]) == norm(g["group"])), None)
        if tgt is None:
            tgt = {"group": g["group"], "items": []}
            ref.append(tgt)
        have = {norm(i["label"]) for i in tgt["items"]}
        tgt["items"] += [i for i in g["items"] if norm(i["label"]) not in have]
    lk = pg.structured.get("breadcrumb_links") or []
    filter_lists.append(fetch_trail_filters([l["url"] for l in lk[1:-1]][:4]))
filters = merge_filters(*filter_lists)
proposal = sp.attach_source_filters(sp.propose_profile(NAME, ref), ref, filters, db=db, company_id=company)
print(f"\n=== {NAME}  <-  {URL}")
print("filters of the category:", ", ".join(f"{f['title']}({len(f['options'])})" for f in filters))
for g in proposal["groups"]:
    on = {e["attribute"]: e for e in proposal["filter_attrs"] if e["group"] == g["name"]}
    print(f"  [{g['name']}] " + " | ".join(a + (f" *{on[a]['kind'][0]}" + (f" <= {on[a]['source_label']}" if on[a]["source_label"] and on[a]["source_label"] != a else "") if a in on else "") for a in g["attributes"]))

# ---- 2. add the new structure next to the old one (the old groups are renamed "~old ..." until the values have moved)
old_groups = db.query(CatalogAttributeGroup).filter(CatalogAttributeGroup.profile_id == prof.id).order_by(CatalogAttributeGroup.sort_order).all()
old_attrs = {g.id: db.query(CatalogAttribute).filter(CatalogAttribute.group_id == g.id).order_by(CatalogAttribute.sort_order).all() for g in old_groups}
old_attr_ids = [a.id for g in old_groups for a in old_attrs[g.id]]
old_gname = {g.id: g.name for g in old_groups}  # the real names, before the temporary "~old" rename
before_count = sum(len(v) for v in old_attrs.values())
on_map = {(e["group"], e["attribute"]): e for e in proposal["filter_attrs"]}
new_items = [
    BulkAttributeGroupItem(
        name=g["name"],
        attributes=[
            BulkAttributeItem(
                name=a,
                field_type="multi_select" if on_map.get((g["name"], a), {}).get("kind") == "multi_select" else None,
                filterable=(g["name"], a) in on_map,
                filter_display_type=on_map.get((g["name"], a), {}).get("kind", "single_select"),
                predefined_values=list(on_map.get((g["name"], a), {}).get("options", [])),
            )
            for a in g["attributes"]
        ],
    )
    for g in proposal["groups"]
]
old_items = [
    BulkAttributeGroupItem(
        id=g.id,
        name=OLD + g.name,
        attributes=[
            BulkAttributeItem(
                id=a.id, name=a.name, field_type=a.field_type, filterable=bool(a.is_filterable),
                filter_display_type=a.filter_display_type or "single_select", storefront_filter_visible=bool(a.storefront_filter_visible),
                predefined_values=sp.parse_json_list(a.predefined_values),
            )
            for a in old_attrs[g.id]
        ],
    )
    for g in old_groups
]
_replace_profile_structure(db, prof.id, AttributeProfileBulkSaveRequest(profile_name=prof.name, image_url=prof.image_url, groups=[*new_items, *old_items]))
db.flush()
fields = sp.profile_fields(db, prof.id)
new_fields = [f for f in fields if not f["group"].startswith(OLD)]

# ---- 3. every product: old values -> the new attributes
products = db.query(CatalogProduct).filter(CatalogProduct.attribute_profile_id == prof.id).all()
new_names = {norm(f["name"]) for f in new_fields}
old_by_name = {norm(a.name): a for g in old_groups for a in old_attrs[g.id]}
state = {}
tot_map = tot_off = tot_left = 0
rejected = curated = 0
# new filter -> the old filter it continues: the same name, else the one whose options overlap most
old_filters = [a for g in old_groups for a in old_attrs[g.id] if a.is_filterable]
counterpart: dict = {}
for f in new_fields:
    if not f["filterable"]:
        continue
    same = old_by_name.get(norm(f["name"]))
    if same is not None and same.is_filterable:
        counterpart[f["id"]] = same
        continue
    fo = {norm(o) for o in f["options"]}
    best = None
    for oa in old_filters:
        oo = {norm(o) for o in sp.parse_json_list(oa.predefined_values)}
        inter = len(fo & oo)
        if inter >= 2 and inter >= 0.5 * min(len(fo), len(oo)) and (best is None or inter > best[0]):
            best = (inter, oa)
    if best:
        counterpart[f["id"]] = best[1]
print("filters continued from the old structure:", ", ".join(f"{f['name']} <= {counterpart[f['id']].name}" for f in new_fields if f["id"] in counterpart) or "none")
for p in products:
    vals = {v.attribute_id: v for v in db.query(V).filter(V.product_id == p.id).all()}
    specs_old = []
    for g in old_groups:
        items = [
            {"label": a.name, "value": ((vals[a.id].display_value or vals[a.id].value) or "").strip()}
            for a in old_attrs[g.id] if a.id in vals and (vals[a.id].value or "").strip()
        ]
        if items:
            specs_old.append({"group": old_gname[g.id], "items": items})
    displays: dict = {}
    values, off, src = sp.map_values_traced(db, company, specs_old, new_fields, context=p.name or "", displays=displays)
    # The old filter values were curated against the shop's own data: where the old structure had the same filter (the same name, or - when the
    # shop names it differently now, "Connection" -> "Interface" - the one whose options overlap), the old value wins over the model's:
    # - it had no value for this product -> a value the model added is dropped (a SATA SSD must not become "Gen3", a membrane combo not "Mechanical");
    # - it had a value that is one of the new options -> that option is used;
    # - a multi-select takes the old selections that are still options (the model is only asked about filters that are new).
    byid0 = {f["id"]: f for f in new_fields}
    multi_done: dict = {}
    for f in new_fields:
        oa = counterpart.get(f["id"])
        if oa is None:
            continue
        ov = vals.get(oa.id)
        oldv = ((ov.value or "").strip() if ov else "")
        opts = {norm(o): o for o in f["options"]}
        if f.get("field_type") == "multi_select":
            parts = [opts[norm(x)] for x in oldv.split(",") if norm(x) in opts]
            if parts:
                multi_done[f["id"]] = ",".join(dict.fromkeys(parts))
            else:
                multi_done[f["id"]] = None
        elif f["id"] in values:
            if not oldv:
                values.pop(f["id"]); displays.pop(f["id"], None); rejected += 1
            elif norm(oldv) in opts and opts[norm(oldv)] != values[f["id"]]:
                values[f["id"]] = opts[norm(oldv)]; displays.pop(f["id"], None); curated += 1
        elif oldv and norm(oldv) in opts:
            values[f["id"]] = opts[norm(oldv)]; curated += 1  # the model left it out but the old structure had it
    sp.fill_product(db, p, prof, {**values, **{k: v for k, v in multi_done.items() if v}}, overwrite=True, displays=displays)
    sp.fill_multi_select(db, p, prof, specs_old, extra_text=p.name or "", skip=set(multi_done))
    used = {src[fid] for fid in values if fid in src}
    used |= {norm(counterpart[fid].name) for fid in counterpart if fid in values or multi_done.get(fid)}  # the old filter row now lives in its continued attribute
    left = [(g["group"], i["label"]) for g in sp._clean_specs(specs_old) for i in g["items"] if norm(i["label"]) not in new_names and norm(i["label"]) not in used]
    state[p.id] = (specs_old, used)
    byid = {f["id"]: f for f in new_fields}
    tot_map += len(values); tot_off += len(off); tot_left += len(left)
    n_filter = sum(1 for fid in values if byid[fid]["filterable"])
    print(f"  {p.name[:56]:<56} {len(sum([g['items'] for g in specs_old], [])):>3} old -> {len(values):>3} mapped ({n_filter} filters), {len(off)} unfit, {len(left):>2} extra")
    if VERBOSE:
        for fid, v in list(values.items())[:60]:
            f = byid[fid]
            if f["filterable"]:
                print(f"       FILTER {f['group']} > {f['name']}: {v}" + (f"   (shown: {displays[fid]})" if fid in displays else ""))
        if left:
            print("       extra specs:", "; ".join(f"{g}>{l}" for g, l in left[:10]) + (" ..." if len(left) > 10 else ""))
    for fid, v in off.items():
        print(f"       UNFIT  {byid[fid]['group']} > {byid[fid]['name']}: '{v}' is not one of its options -> kept as an extra spec")

# ---- 4. the old structure goes (its values have moved or are kept as extra specs); the extra specs are written now that it is gone
db.query(CatalogFilter).filter(CatalogFilter.attribute_id.in_(old_attr_ids)).delete(synchronize_session=False)
db.query(V).filter(V.attribute_id.in_(old_attr_ids)).delete(synchronize_session=False)
db.query(CatalogAttribute).filter(CatalogAttribute.id.in_(old_attr_ids)).delete(synchronize_session=False)
db.query(CatalogAttributeGroup).filter(CatalogAttributeGroup.id.in_([g.id for g in old_groups])).delete(synchronize_session=False)
db.flush()
for p in products:
    specs_old, used = state[p.id]
    extra = sp._leftover_custom_json(db, prof.id, specs_old, used)
    if extra:
        extra = extra.replace('"ai-', '"re-')  # ids of these extra specs must not clash with the ones the import wrote
        cur = json.loads(p.custom_specs_json or "{}") if (p.custom_specs_json or "").strip() else {}
        cur["customGroups"] = [*(cur.get("customGroups") or []), *json.loads(extra)["customGroups"]]
        cur["customAttrs"] = [*(cur.get("customAttrs") or []), *json.loads(extra)["customAttrs"]]
        p.custom_specs_json = json.dumps(cur)
db.flush()
_sync_catalog_filters_for_profile(db, prof.id)
db.flush()

fin_groups = db.query(CatalogAttributeGroup).filter(CatalogAttributeGroup.profile_id == prof.id).order_by(CatalogAttributeGroup.sort_order).all()
n_attr = sum(db.query(CatalogAttribute).filter(CatalogAttribute.group_id == g.id).count() for g in fin_groups)
n_filt = sum(db.query(CatalogAttribute).filter(CatalogAttribute.group_id == g.id, CatalogAttribute.is_filterable.is_(True)).count() for g in fin_groups)
print(f"\nRESULT: {len(old_groups)} groups / {before_count} attributes  ->  {len(fin_groups)} groups / {n_attr} attributes ({n_filt} filterable) | {len(products)} products: {tot_map} values mapped, {tot_off} unfit, {tot_left} kept as extra specs")
print(f"reconciled with the old curated filter values: {rejected} model-added value(s) dropped, {curated} replaced by the old value")
print("leftover '~old' groups:", sum(1 for g in fin_groups if g.name.startswith(OLD)))
if APPLY:
    db.commit()
    print("APPLIED")
else:
    db.rollback()
    print("dry run - rolled back, nothing saved")
