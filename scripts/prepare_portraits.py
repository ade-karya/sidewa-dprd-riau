#!/usr/bin/env python3
"""Menyiapkan potret demo: memangkas watermark dan menormalkan bingkai.

Sumber asli disimpan di ``seed_assets/portraits_source``. Hasil bersih
ditulis ke ``seed_assets/portraits`` agar dapat dipakai seed dan komposit
dokumentasi. Watermark penyedia potret AI berada di tepi atas/bawah,
sehingga pemangkasan vertikal menghilangkannya tanpa merusak wajah.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

BASE = Path(__file__).resolve().parent.parent
SOURCE = BASE / "seed_assets" / "portraits_source"
TARGET = BASE / "seed_assets" / "portraits"

TOP_CROP = 0.11
BOTTOM_CROP = 0.12


def prepare() -> None:
    SOURCE.mkdir(parents=True, exist_ok=True)
    TARGET.mkdir(parents=True, exist_ok=True)

    for path in sorted(SOURCE.glob("*.jpg")):
        target = TARGET / path.name
        image = Image.open(path).convert("RGB")
        width, height = image.size
        top = int(height * TOP_CROP)
        bottom = height - int(height * BOTTOM_CROP)
        cleaned = image.crop((0, top, width, bottom))
        cleaned.save(target, format="JPEG", quality=92, optimize=True, progressive=True)
        print(f"{path.name:16s} {width}x{height} -> {cleaned.width}x{cleaned.height}")


if __name__ == "__main__":
    prepare()
