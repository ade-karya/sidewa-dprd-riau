"""Pengujian alur kegiatan: unggah, terbit, cari, dan akses."""

from pathlib import Path

from PIL import Image

from tests.conftest import get_csrf, login


def _tiny_image(path: Path) -> None:
    image = Image.new("RGB", (96, 96), (126, 72, 144))
    image.save(path, format="JPEG")


def test_activity_create_publish_and_search(seeded_client):
    test_client, tmp = seeded_client
    login(test_client, "superadmin", "Riau#Admin2026")

    photo_path = tmp / "demo.jpg"
    _tiny_image(photo_path)

    token = get_csrf(test_client)
    with photo_path.open("rb") as handle:
        response = test_client.post(
            "/kegiatan",
            data={
                "csrf_token": token,
                "title": "Kegiatan Uji Integrasi",
                "category": "Lainnya",
                "activity_date": "2026-05-01",
                "location_name": "Ruang Uji",
                "description": "Dokumentasi uji integrasi pencarian.",
                "commissions": "I",
            },
            files={"photos": ("demo.jpg", handle, "image/jpeg")},
            follow_redirects=False,
        )
    assert response.status_code in (302, 303)
    location = response.headers.get("location", "")
    assert "/kegiatan/" in location
    activity_id = int(location.rstrip("/").split("/")[-1])

    # Terbitkan
    token = get_csrf(test_client)
    response = test_client.post(
        f"/kegiatan/{activity_id}/terbit",
        data={"csrf_token": token},
        follow_redirects=False,
    )
    assert response.status_code in (302, 303)

    # Detail dapat dibuka
    response = test_client.get(f"/kegiatan/{activity_id}")
    assert response.status_code == 200
    assert "Kegiatan Uji Integrasi" in response.text

    # Pencarian teks menemukan kegiatan
    response = test_client.get("/cari?q=Integrasi")
    assert response.status_code == 200
    assert "Kegiatan Uji Integrasi" in response.text


def test_staf_cannot_create_activity(client):
    from app.constants import ROLE_STAF
    from app.database import SessionLocal
    from app.models import User
    from app.security import hash_password

    db = SessionLocal()
    try:
        if not db.query(User).filter(User.username == "stafuji2").first():
            db.add(
                User(
                    username="stafuji2",
                    full_name="Staf Uji 2",
                    password_hash=hash_password("Staf#Uji2026"),
                    role=ROLE_STAF,
                    is_active=True,
                )
            )
            db.commit()
    finally:
        db.close()

    test_client, _ = client
    login(test_client, "stafuji2", "Staf#Uji2026")
    response = test_client.get("/kegiatan/baru", follow_redirects=False)
    assert response.status_code == 403
