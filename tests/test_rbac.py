"""Pengujian RBAC dan kontrol akses."""


def _create_staf():
    from app.constants import ROLE_STAF
    from app.database import SessionLocal
    from app.models import User
    from app.security import hash_password

    db = SessionLocal()
    try:
        if db.query(User).filter(User.username == "stafuji").first():
            return
        db.add(
            User(
                username="stafuji",
                full_name="Staf Uji",
                password_hash=hash_password("Staf#Uji2026"),
                role=ROLE_STAF,
                is_active=True,
            )
        )
        db.commit()
    finally:
        db.close()


def test_staf_cannot_access_user_management(client):
    from tests.conftest import login

    _create_staf()
    test_client, _ = client
    login(test_client, "stafuji", "Staf#Uji2026")
    response = test_client.get("/pengguna", follow_redirects=False)
    assert response.status_code == 403


def test_staf_cannot_access_audit(client):
    from tests.conftest import login

    _create_staf()
    test_client, _ = client
    login(test_client, "stafuji", "Staf#Uji2026")
    response = test_client.get("/audit", follow_redirects=False)
    assert response.status_code == 403


def test_admin_can_access_user_management(client):
    from tests.conftest import login

    test_client, _ = client
    login(test_client, "superadmin", "Super#Test2026")
    response = test_client.get("/pengguna")
    assert response.status_code == 200


def test_unauthenticated_redirected_to_login(client):
    test_client, _ = client
    response = test_client.get("/kegiatan", follow_redirects=False)
    assert response.status_code in (302, 303)
    assert "/login" in (response.headers.get("location") or "")
