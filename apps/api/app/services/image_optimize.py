"""Uploaded photos / banners / logos are stored as WebP of a sensible size.

A 3000 px JPEG banner or a 770 px logo PNG of 185 KB made the storefront (which serves uploads as they are) slow on phones.
`optimize_upload` turns JPEG / PNG / BMP into WebP (transparency kept) and scales anything wider than MAX_WIDTH down,
and it only ever *replaces* the original when the result is really smaller. WebP, GIF (may be animated), SVG, AVIF and
every non-image file pass through untouched, and any failure falls back to the original bytes: an upload never fails
because of this.
"""
from __future__ import annotations

import logging
from io import BytesIO
from pathlib import Path
from typing import Tuple

log = logging.getLogger(__name__)

# Widest picture kept (px): a 1320 px hero banner on a 2x phone screen is well under it; bigger originals are reduced.
MAX_WIDTH = 1920
# Smallest saving (bytes) worth replacing the original for.
MIN_GAIN = 2 * 1024
WEBP_QUALITY = 82

_CONVERT_EXT = {".jpg", ".jpeg", ".png", ".bmp"}


def optimize_upload(content: bytes, filename: str, mime: str) -> Tuple[bytes, str, str]:
    """Returns (content, filename, mime): the WebP version when it is smaller, otherwise the three values unchanged."""
    ext = Path(filename).suffix.lower()
    if ext not in _CONVERT_EXT or not content:
        return content, filename, mime
    try:
        from PIL import Image, ImageOps

        im = ImageOps.exif_transpose(Image.open(BytesIO(content)))
        has_alpha = im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info)
        im = im.convert("RGBA" if has_alpha else "RGB")
        if im.width > MAX_WIDTH:
            height = max(1, round(im.height * MAX_WIDTH / im.width))
            im = im.resize((MAX_WIDTH, height), Image.LANCZOS)
        out = BytesIO()
        im.save(out, format="WEBP", quality=WEBP_QUALITY, method=6, **({"alpha_quality": 90} if has_alpha else {}))
        data = out.getvalue()
    except Exception:  # noqa: BLE001 - never block an upload over an optimisation
        log.warning("image optimisation skipped for %s", filename, exc_info=True)
        return content, filename, mime
    if len(data) + MIN_GAIN > len(content):
        return content, filename, mime
    return data, f"{Path(filename).stem}.webp", "image/webp"
