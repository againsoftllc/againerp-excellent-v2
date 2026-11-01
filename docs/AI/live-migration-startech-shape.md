# Live migration: Star Tech shape + brand categories

One-time data migration for the v2 live database (Railway project `againerp-excellent`, services `againerp-excellent-v2` + `Postgres-z86y`).
Everything below was done and checked on the local database first; the scripts are idempotent (running them again changes nothing).

## What it does
1. **Profiles** (`scripts/startech_shapes.py` -> `scripts/restructure_profile.py`): the 8 profiles (Motherboard, SSD, Keyboard, Monitor, Mouse, Wi-Fi Router,
   Printer, RAM) lose their "Overview" group and take the shape of a Star Tech product page of that kind: groups and attributes = its specification
   table, the category page's filters sit inside them (same name -> kept, different name -> the filter's name, two filters on one row -> one attribute each).
   Every product's values are mapped by meaning into the new attributes; a value keeps the filter option, the old wording becomes the text the product page
   shows; what has no attribute any more stays on that product as its own extra spec. Nothing is dropped.
2. **Brand categories** (`scripts/backfill_brand_categories.py`): every product is filed under its brand's category, `Components > Motherboard > Gigabyte >
   product`. An existing brand category under the same parent (live already has Dahua / Lenovo / Acer / HP / MSI / Hikvision under Monitor) is reused,
   the others are created with the slug `<brand>-<parent>` (`gigabyte-motherboard`). The product's `category` text stays the TYPE (`Motherboard`).

## Before you run it
* The code of commit `fa94f02` (or later) must be deployed on `againerp-excellent-v2` - check `grep -c brand_level_category app/services/catalog_ai/importer_service.py` inside the container (>= 1).
* The live database differs from the local one: it has one more monitor and a TV product. They are handled like every other product of their profile.
* The AI key of the workspace must work on live (the mapping uses the model): a dry run shows it.
* **Take a backup first.** From a machine that may use the database: `pg_dump -Fc "$DATABASE_PUBLIC_URL" -f before_startech_shapes.dump` (Railway: Postgres-z86y -> Variables).

## Run (inside the API container)
```
railway ssh -s againerp-excellent-v2
cd /app
python scripts/startech_shapes.py                 # DRY RUN of all eight (about 10-15 minutes, rolls back)
python scripts/backfill_brand_categories.py       # DRY RUN
# read both outputs; then
python scripts/startech_shapes.py --apply
python scripts/backfill_brand_categories.py --apply
```
Do ONE profile at a time if you prefer: `python scripts/startech_shapes.py "RAM Specifications" --apply`.

## Check afterwards
* `/website/attributes` in the admin: no "Overview" group; open a product of each profile.
* Storefront: `/motherboard` still lists every motherboard, `/gigabyte-motherboard` lists the Gigabyte ones, a product page's breadcrumb reads
  `Components > Motherboard > Gigabyte > product`.
* The category pages' filters keep their options and counts (Chipset, DRAM Cache, Pack, Features of some profiles are gone on purpose: Star Tech has no such filter).

## Roll back
`pg_restore -d "$DATABASE_PUBLIC_URL" --clean --if-exists before_startech_shapes.dump` (stop the API service first so nothing writes meanwhile).
