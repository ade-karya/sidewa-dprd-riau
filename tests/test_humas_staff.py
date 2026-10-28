"""Pengujian direktori, ruang kerja, dan Face ID staf Humas."""

from pathlib import Path

from tests.conftest import get_csrf, login

PORTRAIT = Path("seed_assets/portraits/p10.jpg")


def _staff(index: int = 0):
    from app.database import SessionLocal
    from app.models import HumasStaff

    db = SessionLocal()
    try:
        rows = (
            db.query(HumasStaff)
            .filter(HumasStaff.is_active.is_(True))
            .order_by(HumasStaff.sort_order)
            .all()
        )
        assert len(rows) == 33
        staff = rows[index]
        return staff.id, staff.full_name
    finally:
        db.close()


def _enroll_staff(test_client, staff_id: int):
    csrf = get_csrf(test_client)
    with PORTRAIT.open("rb") as handle:
        return test_client.post(
            "/login/wajah/daftar",
            data={
                "csrf_token": csrf,
                "subject": f"staff:{staff_id}",
                "consent": "true",
            },
            files={"photo": (PORTRAIT.name, handle, "image/jpeg")},
        )


def test_seeded_staff_directory_and_dashboard(seeded_client):
    test_client, _ = seeded_client
    login(test_client, "superadmin", "Riau#Admin2026")
    staff_id, name = _staff()

    response = test_client.get("/staf-humas")
    assert response.status_code == 200
    assert name in response.text
    assert "Face ID" in response.text

    response = test_client.get(f"/dashboard-staf/{staff_id}")
    assert response.status_code == 200
    assert name in response.text
    assert "Ruang kerja saya" in response.text
    assert "Face ID login" in response.text
    assert "Tugas &amp; fungsi Humas" in response.text


def test_staff_face_enrollment_and_login(seeded_client):
    from app.database import SessionLocal
    from app.models import HumasStaffAccount, HumasStaffFaceLogin

    test_client, _ = seeded_client
    staff_id, name = _staff()

    response = _enroll_staff(test_client, staff_id)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["ok"] is True
    assert payload["redirect"] == f"/dashboard-staf/{staff_id}"

    response = test_client.get(f"/dashboard-staf/{staff_id}")
    assert response.status_code == 200
    assert name in response.text

    db = SessionLocal()
    try:
        account = (
            db.query(HumasStaffAccount)
            .filter(HumasStaffAccount.staff_id == staff_id)
            .first()
        )
        assert account is not None
        assert account.user.role == "staf_humas"
        assert (
            db.query(HumasStaffFaceLogin)
            .filter(HumasStaffFaceLogin.staff_id == staff_id)
            .count()
            == 1
        )
    finally:
        db.close()

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
    assert response.json()["redirect"] == f"/dashboard-staf/{staff_id}"

    response = test_client.get("/", follow_redirects=False)
    assert response.status_code in (302, 303)
    assert response.headers["location"].endswith(f"/dashboard-staf/{staff_id}")


def test_staff_only_sees_own_dashboard(seeded_client):
    test_client, _ = seeded_client
    own_id, _ = _staff(0)
    other_id, _ = _staff(1)

    enrolled = _enroll_staff(test_client, own_id)
    assert enrolled.status_code == 200, enrolled.text

    response = test_client.get(f"/dashboard-staf/{own_id}")
    assert response.status_code == 200

    response = test_client.get(f"/dashboard-staf/{other_id}")
    assert response.status_code == 403

    response = test_client.get("/staf-humas")
    assert response.status_code == 200
    assert "Ruang kerja pribadi" in response.text


def test_admin_can_delete_staff_face_login(seeded_client):
    from app.database import SessionLocal
    from app.models import HumasStaffFaceLogin

    test_client, _ = seeded_client
    staff_id, _ = _staff()

    enrolled = _enroll_staff(test_client, staff_id)
    assert enrolled.status_code == 200, enrolled.text

    csrf = get_csrf(test_client)
    test_client.post("/logout", data={"csrf_token": csrf}, follow_redirects=False)

    login(test_client, "superadmin", "Riau#Admin2026")
    csrf = get_csrf(test_client)
    response = test_client.post(
        f"/staf-humas/{staff_id}/face-login/hapus",
        data={"csrf_token": csrf},
        follow_redirects=False,
    )
    assert response.status_code in (302, 303)

    db = SessionLocal()
    try:
        assert (
            db.query(HumasStaffFaceLogin)
            .filter(HumasStaffFaceLogin.staff_id == staff_id)
            .count()
            == 0
        )
    finally:
        db.close()
