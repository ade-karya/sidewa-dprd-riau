"""Pengujian helper path media (gambar utama vs thumbnail)."""

from __future__ import annotations

from app.services.images import full_path, path_variants, thumb_path


def test_thumb_and_full_path_roundtrip():
    main = "staff/2026/10/abc_1234.jpg"
    thumb = "staff/2026/10/abc_1234_thumb.jpg"

    assert thumb_path(main) == thumb
    assert full_path(thumb) == main
    assert thumb_path(thumb) == thumb
    assert full_path(main) == main


def test_path_variants_puts_requested_path_first():
    main = "members/2026/10/a.jpg"
    thumb = "members/2026/10/a_thumb.jpg"

    assert path_variants(main) == [main, thumb]
    assert path_variants(thumb) == [thumb, main]


def test_helpers_handle_empty_and_non_jpeg():
    assert thumb_path(None) is None
    assert full_path(None) is None
    assert thumb_path("staff/x.png") == "staff/x_thumb.png"
    assert full_path("staff/x_thumb.png") == "staff/x.png"


def test_save_image_keeps_main_and_paired_thumb(tmp_path, monkeypatch):
    from io import BytesIO

    from PIL import Image

    from app.services import images, media_sync

    monkeypatch.setattr(images.settings, "media_root", tmp_path)
    monkeypatch.setattr(media_sync, "enqueue_upload", lambda path: None)

    buf = BytesIO()
    Image.new("RGB", (800, 1000), "red").save(buf, format="JPEG")

    main, thumb, width, height = images.save_image(
        buf.getvalue(), "staff", max_dimension=2000, thumb_dimension=1200
    )

    assert (width, height) == (800, 1000)
    assert thumb == thumb_path(main)
    assert (tmp_path / main).is_file()
    assert (tmp_path / thumb).is_file()
    assert Image.open(tmp_path / main).size == (800, 1000)
