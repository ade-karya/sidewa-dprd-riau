#!/usr/bin/env python3
"""Membuat foto dokumentasi demo dari potret AI-generated.

Aset ini hanya untuk demo. Wajah dibuat oleh this-person-does-not-exist.com
dan bukan orang sungguhan.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

BASE = Path(__file__).resolve().parent.parent
PORTRAITS = BASE / "seed_assets" / "portraits"
BACKGROUNDS = BASE / "seed_assets" / "backgrounds"
OUT = BASE / "seed_assets" / "activities"
OUT.mkdir(parents=True, exist_ok=True)

FONT_DIR = Path("/usr/share/fonts/truetype/freefont")
FONT_BOLD = FONT_DIR / "FreeSansBold.ttf"
FONT_REG = FONT_DIR / "FreeSans.ttf"

PORTRAIT_FILES = {
    1: "p10.jpg",
    2: "p3.jpg",
    3: "x15.jpg",
    4: "p4.jpg",
    5: "p6.jpg",
    6: "p5.jpg",
    7: "p2.jpg",
    8: "p14.jpg",
    9: "p8.jpg",
    10: "p11.jpg",
    11: "x14.jpg",
    12: "p16.jpg",
    13: "x13.jpg",
    14: "p7.jpg",
    15: "extra04.jpg",
    16: "x16.jpg",
}

ACTIVITIES = [
    {
        "slug": "paripurna-apbd",
        "title": "Rapat Paripurna Pengesahan APBD Provinsi Riau Tahun 2026",
        "category": "Rapat Paripurna",
        "people": [1, 2, 3, 4, 5, 8],
        "bg": "hall.jpg",
    },
    {
        "slug": "kerja-komisi-ii",
        "title": "Rapat Kerja Komisi II Evaluasi Realisasi APBD",
        "category": "Rapat Kerja",
        "people": [8, 9, 10],
        "bg": "meeting.jpg",
    },
    {
        "slug": "kunker-komisi-iii",
        "title": "Kunjungan Kerja Komisi III ke Kabupaten Kampar",
        "category": "Kunjungan Kerja",
        "people": [11, 12],
        "bg": "office.jpg",
    },
    {
        "slug": "rdp-komisi-iv",
        "title": "Rapat Dengar Pendapat Komisi IV bersama Tenaga Kesehatan",
        "category": "Rapat Dengar Pendapat",
        "people": [13, 14],
        "bg": "conference.jpg",
    },
    {
        "slug": "reses-komisi-i",
        "title": "Reses Masa Sidang III di Daerah Pemilihan Riau I",
        "category": "Reses",
        "people": [5, 6, 7, 1],
        "bg": "meeting.jpg",
    },
    {
        "slug": "sosialisasi-perda",
        "title": "Sosialisasi Perda Perlindungan Anak di Sekolah Dasar",
        "category": "Sosialisasi",
        "people": [13, 14, 2],
        "bg": "hall.jpg",
    },
    {
        "slug": "monitoring-siak",
        "title": "Monitoring Infrastruktur Jalan Provinsi di Kabupaten Siak",
        "category": "Monitoring",
        "people": [11, 12, 3],
        "bg": "office.jpg",
    },
    {
        "slug": "kerja-komisi-v",
        "title": "Rapat Kerja Komisi V Penanganan Karhutla",
        "category": "Rapat Kerja",
        "people": [15, 16, 4],
        "bg": "conference.jpg",
    },
    {
        "slug": "audiensi-pesisir",
        "title": "Audiensi Masyarakat Pesisir bersama Komisi II dan Komisi V",
        "category": "Rapat Dengar Pendapat",
        "people": [8, 10, 15, 16],
        "bg": "meeting.jpg",
    },
    {
        "slug": "pelantikan-paw",
        "title": "Pelantikan Anggota Pengganti Antar Waktu DPRD Riau",
        "category": "Pelantikan",
        "people": [1, 2, 3, 4, 5],
        "bg": "hall.jpg",
    },
    {
        "slug": "rakor-akhir-tahun",
        "title": "Rapat Koordinasi Evaluasi Kinerja Akhir Tahun 2025",
        "category": "Rapat Kerja",
        "people": [1, 2, 5],
        "bg": "conference.jpg",
    },
]


def font(path: Path, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(path), size)


def cover(path: Path, size: tuple[int, int]) -> Image.Image:
    img = Image.open(path).convert("RGB")
    return ImageOps.fit(img, size, method=Image.Resampling.LANCZOS)


def make_background(name: str) -> Image.Image:
    bg = Image.open(BACKGROUNDS / name).convert("RGB")
    bg = ImageOps.fit(bg, (1600, 1000), method=Image.Resampling.LANCZOS)
    bg = bg.filter(ImageFilter.GaussianBlur(14))
    bg = ImageEnhance.Brightness(bg).enhance(0.44)
    bg = ImageEnhance.Color(bg).enhance(0.9)

    overlay = Image.new("RGBA", bg.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    # Gradasi atas agar badge/tombol HTML tetap terbaca.
    for y in range(360):
        alpha = int(135 * (1 - y / 360) ** 1.4)
        draw.line([(0, y), (1600, y)], fill=(23, 10, 30, alpha))
    # Gradasi bawah untuk tanggal dan jumlah foto pada kartu.
    for y in range(620, 1000):
        alpha = int(185 * ((y - 620) / 380) ** 1.25)
        draw.line([(0, y), (1600, y)], fill=(23, 10, 30, alpha))
    return Image.alpha_composite(bg.convert("RGBA"), overlay)


def portrait_card(index: int, size: tuple[int, int], radius: int = 24) -> Image.Image:
    source = Image.open(PORTRAITS / PORTRAIT_FILES[index]).convert("RGB")
    img = ImageOps.fit(source, size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.32))
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, size[0] - 1, size[1] - 1], radius=radius, fill=255
    )
    card = Image.new("RGBA", size, (0, 0, 0, 0))
    card.paste(img, (0, 0), mask)

    framed = Image.new("RGBA", (size[0] + 8, size[1] + 8), (0, 0, 0, 0))
    frame = Image.new("RGBA", framed.size, (0, 0, 0, 0))
    ImageDraw.Draw(frame).rounded_rectangle(
        [0, 0, framed.width - 1, framed.height - 1],
        radius=radius + 4,
        fill=(255, 255, 255, 210),
    )
    framed.alpha_composite(frame)
    framed.alpha_composite(card, (4, 4))
    return framed


def compose(activity: dict, variant: int) -> Image.Image:
    canvas = make_background(activity["bg"])

    people = activity["people"]
    if variant == 2:
        people = people[:2] if len(people) > 2 else people

    count = len(people)
    if count <= 2:
        pw, ph, gap = 330, 420, 26
    elif count == 3:
        pw, ph, gap = 300, 385, 20
    elif count == 4:
        pw, ph, gap = 265, 345, 16
    else:
        pw, ph, gap = 232, 305, 12

    total_width = count * pw + (count - 1) * gap
    start_x = (1600 - total_width) // 2
    base_y = 872 - ph

    # Bayangan lembut di bawah setiap bingkai.
    shadows = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadows)
    for idx in range(count):
        x = start_x + idx * (pw + gap) - 4
        y = base_y + (0 if idx % 2 == 0 else 10)
        shadow_draw.rounded_rectangle(
            [x + 8, y + 16, x + pw + 8, y + ph + 16],
            radius=30,
            fill=(0, 0, 0, 120),
        )
    canvas.alpha_composite(shadows.filter(ImageFilter.GaussianBlur(16)))

    for idx, person in enumerate(people):
        card = portrait_card(person, (pw, ph))
        x = start_x + idx * (pw + gap) - 4
        y = base_y + (0 if idx % 2 == 0 else 10)
        canvas.alpha_composite(card, (x - 4, y - 4))

    draw = ImageDraw.Draw(canvas)
    pill_x, pill_y = 1300, 922
    draw.rounded_rectangle(
        [pill_x, pill_y, pill_x + 232, pill_y + 36],
        radius=18,
        fill=(23, 10, 30, 165),
        outline=(255, 255, 255, 45),
    )
    draw.text(
        (pill_x + 18, pill_y + 9),
        "SIMULASI DEMO",
        font=font(FONT_BOLD, 15),
        fill=(224, 190, 255, 235),
    )
    draw.text(
        (64, 936),
        "SIDEWA · Dokumentasi DPRD Provinsi Riau",
        font=font(FONT_REG, 15),
        fill=(255, 255, 255, 120),
    )
    return canvas.convert("RGB")


def main() -> None:
    for activity in ACTIVITIES:
        for variant in (1, 2):
            image = compose(activity, variant)
            path = OUT / f"{activity['slug']}-{variant}.jpg"
            image.save(path, format="JPEG", quality=88, optimize=True, progressive=True)
            print(path.name, image.size)


if __name__ == "__main__":
    main()
