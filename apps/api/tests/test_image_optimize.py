from io import BytesIO

from PIL import Image

from app.services.image_optimize import MAX_WIDTH, optimize_upload


def _jpeg(w, h):
    # noisy-ish gradient so the JPEG is not trivially tiny
    im = Image.effect_noise((w, h), 60).convert("RGB")
    out = BytesIO()
    im.save(out, format="JPEG", quality=95)
    return out.getvalue()


def test_big_jpeg_becomes_smaller_webp_within_max_width():
    src = _jpeg(3000, 1200)
    data, name, mime = optimize_upload(src, "Hero Banner.JPG", "image/jpeg")
    assert name == "Hero Banner.webp" and mime == "image/webp"
    assert len(data) < len(src)
    im = Image.open(BytesIO(data))
    assert im.format == "WEBP" and im.width == MAX_WIDTH


def test_png_with_transparency_keeps_alpha():
    im = Image.new("RGBA", (800, 300), (0, 0, 0, 0))
    for x in range(0, 800, 7):
        for y in range(0, 300, 5):
            im.putpixel((x, y), (200, 30, 90, 255))
    out = BytesIO()
    im.save(out, format="PNG")
    src = out.getvalue()
    data, name, mime = optimize_upload(src, "logo.png", "image/png")
    if mime == "image/webp":  # converted only when it is really smaller
        assert Image.open(BytesIO(data)).mode == "RGBA"
    assert len(data) <= len(src) + 2048


def test_untouchable_files_pass_through():
    for fname, mime in [("a.webp", "image/webp"), ("a.gif", "image/gif"), ("a.svg", "image/svg+xml"), ("a.pdf", "application/pdf")]:
        assert optimize_upload(b"abc", fname, mime) == (b"abc", fname, mime)


def test_garbage_bytes_fall_back_to_original():
    assert optimize_upload(b"not an image", "x.jpg", "image/jpeg") == (b"not an image", "x.jpg", "image/jpeg")


def test_small_jpeg_is_left_alone_when_no_gain():
    src = _jpeg(40, 40)
    data, name, mime = optimize_upload(src, "tiny.jpg", "image/jpeg")
    assert (name, mime) in {("tiny.jpg", "image/jpeg"), ("tiny.webp", "image/webp")}
    assert len(data) <= len(src)
