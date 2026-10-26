"""Pengujian pendaftaran dan login Face ID anggota dewan."""

from pathlib import Path

from tests.conftest import get_csrf, login

PORTRAIT = Path("seed_assets/portraits/p10.jpg")


def _first_member():
    from app.database import SessionLocal
    from app.models import Member

    db = SessionLocal()
    try:
        member = db.query(Member).filter(Member.is_active.is_(True)).order_by(Member.id).first()
        assert member is not None
        return member.id, member.full_name
    finally:
        db.close()


def _enroll_with_face(test_client, member_id: int):
    csrf = get_csrf(test_client)
    with PORTRAIT.open("rb") as handle:
        return test_client.post(
            "/login/wajah/daftar",
            data={
                "csrf_token": csrf,
                "member_id": str(member_id),
                "consent": "true",
            },
            files={"photo": (PORTRAIT.name, handle, "image/jpeg")},
        )


def test_face_login_enrollment_creates_account_and_session(seeded_client):
    from app.database import SessionLocal
    from app.models import MemberAccount, MemberFaceLogin, User

    test_client, _ = seeded_client
    member_id, name = _first_member()

    response = _enroll_with_face(test_client, member_id)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["ok"] is True
    assert payload["name"] == name
    assert payload["redirect"] == f"/dashboard-anggota/{member_id}"

    response = test_client.get(f"/dashboard-anggota/{member_id}")
    assert response.status_code == 200
    assert name in response.text

    db = SessionLocal()
    try:
        account = db.query(MemberAccount).filter(MemberAccount.member_id == member_id).first()
        assert account is not None
        assert account.user.role == "anggota_dewan"
        assert account.user.is_active is True
        assert (
            db.query(MemberFaceLogin)
            .filter(MemberFaceLogin.member_id == member_id)
            .count()
            == 1
        )
        user_count = db.query(User).filter(User.username == f"anggota{member_id}").count()
        assert user_count == 1
    finally:
        db.close()


def test_face_login_rejects_duplicate_enrollment(seeded_client):
    test_client, _ = seeded_client
    member_id, _ = _first_member()

    first = _enroll_with_face(test_client, member_id)
    assert first.status_code == 200, first.text

    # Keluar lalu coba daftarkan ulang anggota yang sama.
    csrf = get_csrf(test_client)
    test_client.post("/logout", data={"csrf_token": csrf}, follow_redirects=False)

    second = _enroll_with_face(test_client, member_id)
    assert second.status_code == 409
    assert "sudah terdaftar" in second.json()["error"]


def test_face_scan_logs_in_after_logout(seeded_client):
    test_client, _ = seeded_client
    member_id, name = _first_member()

    enrolled = _enroll_with_face(test_client, member_id)
    assert enrolled.status_code == 200, enrolled.text

    csrf = get_csrf(test_client)
    test_client.post("/logout", data={"csrf_token": csrf}, follow_redirects=False)

    csrf = get_csrf(test_client)
    with PORTRAIT.open("rb") as handle:
        response = test_client.post(
            "/login/wajah",
            data={"csrf_token": csrf},
            files={"photo": (PORTRAIT.name, handle, "image/jpeg")},
        )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["ok"] is True
    assert payload["name"] == name
    assert payload["redirect"] == f"/dashboard-anggota/{member_id}"

    response = test_client.get(f"/dashboard-anggota/{member_id}")
    assert response.status_code == 200


def test_admin_can_delete_face_login(seeded_client):
    from app.database import SessionLocal
    from app.models import MemberFaceLogin

    test_client, _ = seeded_client
    member_id, _ = _first_member()

    enrolled = _enroll_with_face(test_client, member_id)
    assert enrolled.status_code == 200, enrolled.text

    csrf = get_csrf(test_client)
    test_client.post("/logout", data={"csrf_token": csrf}, follow_redirects=False)

    login(test_client, "superadmin", "Riau#Admin2026")
    csrf = get_csrf(test_client)
    response = test_client.post(
        f"/anggota/{member_id}/face-login/hapus",
        data={"csrf_token": csrf},
        follow_redirects=False,
    )
    assert response.status_code in (302, 303)

    db = SessionLocal()
    try:
        assert (
            db.query(MemberFaceLogin)
            .filter(MemberFaceLogin.member_id == member_id)
            .count()
            == 0
        )
    finally:
        db.close()
