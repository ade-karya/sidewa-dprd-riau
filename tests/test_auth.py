"""Pengujian autentikasi, CSRF, dan sesi."""

from tests.conftest import get_csrf, login


def test_login_page_has_sidewa_guide(client):
    test_client, _ = client
    response = test_client.get("/login")
    assert response.status_code == 200
    assert "Kenali SIDEWA" in response.text
    assert "app-guide.js" in response.text


def test_login_success_sets_session(client):
    test_client, _ = client
    login(test_client, "superadmin", "Super#Test2026")
    response = test_client.get("/")
    assert response.status_code == 200
    assert "superadmin" in response.text.lower() or "Super Admin" in response.text


def test_login_failure_does_not_authenticate(client):
    test_client, _ = client
    token = get_csrf(test_client)
    response = test_client.post(
        "/login",
        data={"username": "superadmin", "password": "salah", "csrf_token": token, "next": "/"},
        follow_redirects=False,
    )
    assert response.status_code == 401
    response = test_client.get("/", follow_redirects=False)
    assert response.status_code in (302, 303)


def test_post_without_csrf_is_rejected(client):
    test_client, _ = client
    login(test_client, "superadmin", "Super#Test2026")
    # Token lama/salah
    response = test_client.post(
        "/kegiatan",
        data={
            "title": "X",
            "category": "Lainnya",
            "activity_date": "2026-01-01",
            "location_name": "Y",
        },
        follow_redirects=False,
    )
    assert response.status_code == 403


def test_logout_ends_session(client):
    test_client, _ = client
    login(test_client, "superadmin", "Super#Test2026")
    token = get_csrf(test_client)
    test_client.post("/logout", data={"csrf_token": token}, follow_redirects=False)
    response = test_client.get("/", follow_redirects=False)
    assert response.status_code in (302, 303)
