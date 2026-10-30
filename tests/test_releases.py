"""Pengujian fitur rilis (siaran pers) Humas."""

from __future__ import annotations

from datetime import date

from tests.conftest import get_csrf, login


def _activity_id() -> int:
    from app.constants import STATUS_PUBLISHED
    from app.database import SessionLocal
    from app.models import Activity

    db = SessionLocal()
    try:
        activity = (
            db.query(Activity)
            .filter(Activity.status == STATUS_PUBLISHED)
            .order_by(Activity.activity_date.desc())
            .first()
        )
        assert activity is not None
        return activity.id
    finally:
        db.close()


def test_humas_can_create_and_publish_release(seeded_client):
    from app.constants import STATUS_DRAFT, STATUS_PUBLISHED
    from app.database import SessionLocal
    from app.models import PressRelease

    test_client, _ = seeded_client
    login(test_client, "humas", "Humas#Riau2026")
    csrf = get_csrf(test_client)

    response = test_client.post(
        "/rilis",
        data={
            "csrf_token": csrf,
            "title": "DPRD Riau Dorong Percepatan Pembangunan Infrastruktur Daerah",
            "summary": "Komisi IV meninjau progres jalan provinsi dan meminta percepatan.",
            "body": (
                "PEKANBARU — DPRD Provinsi Riau mendorong percepatan pembangunan "
                "infrastruktur jalan provinsi agar konektivitas antarkabupaten meningkat.\n\n"
                "Komisi IV menegaskan bahwa anggaran yang tersedia harus dikawal agar "
                "tepat sasaran dan transparan."
            ),
            "release_date": date.today().isoformat(),
            "activity_id": str(_activity_id()),
            "tags": "Infrastruktur, Pembangunan, Komisi IV",
        },
        follow_redirects=False,
    )
    assert response.status_code in (302, 303), response.text
    location = response.headers["location"]
    assert location.startswith("/rilis/")
    release_id = int(location.rsplit("/", 1)[1])

    db = SessionLocal()
    try:
        release = db.get(PressRelease, release_id)
        assert release is not None
        assert release.status == STATUS_DRAFT
        assert release.code.startswith("RIL-")
        assert release.slug.startswith("dprd-riau-dorong")
        assert release.tag_list == ["Infrastruktur", "Pembangunan", "Komisi IV"]
    finally:
        db.close()

    response = test_client.get("/rilis")
    assert response.status_code == 200
    assert "DPRD Riau Dorong Percepatan" in response.text
    assert "Draf" in response.text

    csrf = get_csrf(test_client)
    response = test_client.post(
        f"/rilis/{release_id}/terbit",
        data={"csrf_token": csrf},
        follow_redirects=False,
    )
    assert response.status_code in (302, 303)

    db = SessionLocal()
    try:
        release = db.get(PressRelease, release_id)
        assert release is not None
        assert release.status == STATUS_PUBLISHED
        assert release.published_at is not None
    finally:
        db.close()

    response = test_client.get(f"/rilis/{release_id}")
    assert response.status_code == 200
    assert "DPRD Riau Dorong Percepatan" in response.text
    assert "Komisi IV" in response.text


def test_staff_workspace_shows_release_summary(seeded_client):
    from app.constants import STATUS_PUBLISHED
    from app.database import SessionLocal
    from app.models import HumasStaff, HumasStaffAccount, PressRelease, utcnow

    test_client, _ = seeded_client

    db = SessionLocal()
    try:
        staff = (
            db.query(HumasStaff)
            .filter(HumasStaff.is_active.is_(True))
            .order_by(HumasStaff.sort_order)
            .first()
        )
        assert staff is not None
        account = (
            db.query(HumasStaffAccount)
            .filter(HumasStaffAccount.staff_id == staff.id)
            .first()
        )
        assert account is not None
        release = PressRelease(
            code="RIL-2026-9001",
            title="Rilis Uji Ruang Kerja Staf Humas",
            slug="rilis-uji-ruang-kerja-staf-humas",
            summary="Ringkasan rilis untuk pengujian ruang kerja.",
            body=(
                "PEKANBARU — Rilis ini dipakai untuk memastikan ringkasan rilis "
                "tampil pada ruang kerja staf Humas di SIDEWA."
            ),
            status=STATUS_PUBLISHED,
            release_date=date.today(),
            author_id=account.user_id,
            published_at=utcnow(),
        )
        db.add(release)
        db.commit()
        staff_id = staff.id
    finally:
        db.close()

    login(test_client, "superadmin", "Riau#Admin2026")
    response = test_client.get(f"/dashboard-staf/{staff_id}")
    assert response.status_code == 200
    assert "Rilis &amp; siaran pers" in response.text
    assert "Tulis rilis" in response.text
    assert "Rilis Uji Ruang Kerja Staf Humas" in response.text


def test_release_visibility_and_rbac(seeded_client):
    from app.constants import STATUS_DRAFT, STATUS_PUBLISHED
    from app.database import SessionLocal
    from app.models import PressRelease, User

    test_client, _ = seeded_client

    db = SessionLocal()
    try:
        humas = db.query(User).filter(User.username == "humas").first()
        assert humas is not None
        published = PressRelease(
            code="RIL-2026-9002",
            title="Rilis Terbit Untuk Semua Pengguna",
            slug="rilis-terbit-untuk-semua-pengguna",
            summary="Rilis terbit.",
            body=(
                "PEKANBARU — Rilis terbit ini dapat dibaca oleh seluruh pengguna "
                "yang telah masuk ke aplikasi SIDEWA."
            ),
            status=STATUS_PUBLISHED,
            release_date=date.today(),
            author_id=humas.id,
        )
        draft = PressRelease(
            code="RIL-2026-9003",
            title="Draf Rilis Khusus Pengelola Konten",
            slug="draf-rilis-khusus-pengelola-konten",
            summary="Draf rilis.",
            body=(
                "PEKANBARU — Draf ini hanya boleh dibaca oleh pengelola konten "
                "dan administrator SIDEWA."
            ),
            status=STATUS_DRAFT,
            release_date=date.today(),
            author_id=humas.id,
        )
        db.add_all([published, draft])
        db.commit()
        published_id = published.id
        draft_id = draft.id
    finally:
        db.close()

    login(test_client, "komisi1", "Komisi1#Riau2026")

    response = test_client.get("/rilis")
    assert response.status_code == 200
    assert "Rilis Terbit Untuk Semua Pengguna" in response.text
    assert "Draf Rilis Khusus Pengelola Konten" not in response.text

    assert test_client.get(f"/rilis/{published_id}").status_code == 200
    assert test_client.get(f"/rilis/{draft_id}").status_code == 404
    assert test_client.get("/rilis/baru").status_code == 403

    csrf = get_csrf(test_client)
    response = test_client.post(
        "/rilis",
        data={
            "csrf_token": csrf,
            "title": "Upaya Membuat Rilis Tanpa Izin",
            "body": "Isi rilis yang tidak boleh dibuat oleh staf komisi.",
            "release_date": date.today().isoformat(),
        },
        follow_redirects=False,
    )
    assert response.status_code == 403
