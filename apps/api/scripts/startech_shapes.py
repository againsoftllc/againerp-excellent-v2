"""One-time data migration: bring the attribute profiles into the source shop's own shape (Star Tech) and file every product under its brand category.

Run INSIDE the API container (it needs the app's DB, its AI key and its code), dry run first - a dry run does everything, then rolls back:

    python scripts/startech_shapes.py                      # dry run, every profile below
    python scripts/startech_shapes.py "RAM Specifications" # dry run, one profile
    python scripts/startech_shapes.py --apply              # apply (back the database up first!)
    python scripts/backfill_brand_categories.py            # dry run: Components > Motherboard > Gigabyte > product
    python scripts/backfill_brand_categories.py --apply

Order: profiles first, then the brand categories. Per profile: groups / attributes become the product page's specification table, the category
page's filters sit inside them, every product's values are mapped by meaning into the new attributes (what has no attribute stays on that product
as its own extra spec - nothing is dropped). See docs/AI/product-upload.md (A11, A10).
"""
import subprocess
import sys

S = "https://www.startech.com.bd"
SHAPES = {
    "Motherboard Specifications": [f"{S}/gigabyte-h610m-k-ddr4-motherboard"],
    "SSD Specifications": [f"{S}/corsair-mp600-gs-500gb-pcie-nvme-ssd"],
    "Keyboard Specifications": [f"{S}/logitech-mx-keys-s-keyboard"],
    "Monitor Specifications": [f"{S}/asus-tuf-gaming-vg249qm5f-monitor", f"{S}/lg-ultragear-32gs95uv-b-gaming-monitor"],
    "Mouse Specifications": [f"{S}/razer-deathadder-essential-gaming-mouse-white", f"{S}/logitech-g304-hero-lightspeed-wireless-gaming-mouse"],
    "Wi-Fi Router Specifications": [f"{S}/tp-link-archer-ax73-ax5400-dual-band-gigabit-router", f"{S}/asus-rt-axe7800-tri-band-gaming-router"],
    "Printer Specifications": [f"{S}/hp-laserjet-pro-4002dn-printer", f"{S}/epson-ecotank-m1120-printer"],
    "RAM Specifications": [f"{S}/kingston-fury-beast-16gb-3200mhz-ddr4-desktop-ram", f"{S}/corsair-vengeance-rgb-16gb-ddr5-7200mhz-desktop-ram"],
}

if __name__ == "__main__":
    apply = "--apply" in sys.argv
    only = [a for a in sys.argv[1:] if not a.startswith("--")]
    for name, urls in SHAPES.items():
        if only and name not in only:
            continue
        print(f"\n######## {name}", flush=True)
        rc = subprocess.call([sys.executable, "scripts/restructure_profile.py", name, *urls, *(["--apply"] if apply else [])])
        if rc != 0:
            sys.exit(f"stopped at {name} (exit {rc}) - nothing after it was run")
