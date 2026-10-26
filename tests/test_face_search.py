"""Pengujian pencarian wajah dan API."""

from pathlib import Path

from tests.conftest import get_csrf, login

TEST_MEMBER_NAME = "Anggota Uji Wajah"


def _enroll_test_face() -> None:
    """Daftarkan satu wajah uji pada anggota fiktif khusus pengujian."""
    from app.constants import STATUS_PUBLISHED
    from app.database import SessionLocal
    from app.models import Activity, ActivityMember, Member, MemberFace
    from app.services import face_engine
    from app.services.images import copy_seed_image

    source = Path("seed_assets/portraits/p10.jpg")
    db = SessionLocal()
    try:
        member = Member(
            full_name=TEST_MEMBER_NAME,
            position="Anggota Komisi I",
            party="Uji",
            dapil="Riau 1",
            is_active=True,
        )
        db.add(member)
        db.flush()

        rel_main, rel_thumb, _, _ = copy_seed_image(source, "members")
        member.portrait_path = rel_thumb
        detected = face_engine.engine.detect_single(source)
        db.add(
            MemberFace(
                member_id=member.id,
                image_path=rel_main,
                encoding=detected.encoding,
                quality=detected.quality,
                is_primary=True,
                source="test",
            )
        )

        activity = (
            db.query(Activity)
            .filter(Activity.status == STATUS_PUBLISHED)
            .order_by(Activity.id)
            .first()
        )
        if activity:
            db.add(
                ActivityMember(
                    activity_id=activity.id,
                    member_id=member.id,
                    source="manual",
                    confirmed=True,
                )
            )
        db.commit()
    finally:
        db.close()


def test_face_search_finds_known_member(seeded_client):
    test_client, _ = seeded_client
    _enroll_test_face()
    login(test_client, "komisi1", "Komisi1#Riau2026")
    token = get_csrf(test_client)

    with open("seed_assets/portraits/p10.jpg", "rb") as handle:
        response = test_client.post(
            "/cari/wajah",
            data={"csrf_token": token, "tolerance": "0.60"},
            files={"photo": ("p10.jpg", handle, "image/jpeg")},
        )
    assert response.status_code == 200
    assert TEST_MEMBER_NAME in response.text
    assert "anggota cocok" in response.text


def test_api_face_search_with_bearer_token(seeded_client):
    test_client, _ = seeded_client
    _enroll_test_face()
    login(test_client, "komisi1", "Komisi1#Riau2026")

    # Buat token API
    token = get_csrf(test_client)
    response = test_client.post(
        "/profil/token",
        data={"csrf_token": token, "name": "Uji API", "days": "30"},
        follow_redirects=False,
    )
    assert response.status_code in (302, 303)

    # Ambil token dari halaman profil
    response = test_client.get("/profil")
    assert response.status_code == 200
    import re

    match = re.search(r"id=\"new-token-value\">([^<]+)<", response.text)
    assert match, "Token baru tidak ditampilkan"
    api_token = match.group(1).strip()

    with open("seed_assets/portraits/p10.jpg", "rb") as handle:
        response = test_client.post(
            "/api/v1/search/face",
            headers={"Authorization": f"Bearer {api_token}"},
            files={"photo": ("p10.jpg", handle, "image/jpeg")},
        )
    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["query_faces"] == 1
    assert payload["matches"]
    assert payload["matches"][0]["member"]["full_name"] == TEST_MEMBER_NAME
    assert len(payload["activities"]) >= 1


def test_api_me_requires_auth(seeded_client):
    test_client, _ = seeded_client
    response = test_client.get("/api/v1/me")
    assert response.status_code == 401
