"""Pengujian pencarian wajah dan API."""

from tests.conftest import get_csrf, login


def test_face_search_finds_known_member(seeded_client):
    test_client, _ = seeded_client
    login(test_client, "komisi1", "Komisi1#Riau2026")
    token = get_csrf(test_client)

    with open("seed_assets/portraits/p10.jpg", "rb") as handle:
        response = test_client.post(
            "/cari/wajah",
            data={"csrf_token": token, "tolerance": "0.60"},
            files={"photo": ("p10.jpg", handle, "image/jpeg")},
        )
    assert response.status_code == 200
    assert "H. Ahmad Fauzan" in response.text
    assert "anggota cocok" in response.text


def test_api_face_search_with_bearer_token(seeded_client):
    test_client, _ = seeded_client
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
    assert payload["matches"][0]["member"]["full_name"].startswith("H. Ahmad Fauzan")
    assert len(payload["activities"]) >= 1


def test_api_me_requires_auth(seeded_client):
    test_client, _ = seeded_client
    response = test_client.get("/api/v1/me")
    assert response.status_code == 401
