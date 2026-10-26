"""Pengujian dashboard anggota dewan dan akses sentimen."""

from tests.conftest import get_csrf, login


def _member(commission_code: str | None = None):
    from app.database import SessionLocal
    from app.models import Commission, Member

    db = SessionLocal()
    try:
        query = db.query(Member).filter(Member.is_active.is_(True))
        if commission_code:
            query = query.join(Commission, Member.commission_id == Commission.id).filter(
                Commission.code == commission_code
            )
        member = query.order_by(Member.id).first()
        assert member is not None
        return member.id, member.full_name
    finally:
        db.close()


def _create_member_account(member_id: int, username: str = "ujianggota") -> None:
    from app.constants import ROLE_ANGGOTA
    from app.database import SessionLocal
    from app.models import MemberAccount, User
    from app.security import hash_password

    db = SessionLocal()
    try:
        existing = db.query(User).filter(User.username == username).first()
        if existing:
            return
        user = User(
            username=username,
            full_name="Anggota Uji Dashboard",
            password_hash=hash_password("Anggota#Uji2026"),
            role=ROLE_ANGGOTA,
            is_active=True,
        )
        db.add(user)
        db.flush()
        db.add(MemberAccount(user_id=user.id, member_id=member_id))
        db.commit()
    finally:
        db.close()


def test_admin_can_open_member_dashboard(seeded_client):
    test_client, _ = seeded_client
    login(test_client, "superadmin", "Riau#Admin2026")
    member_id, name = _member()

    response = test_client.get(f"/dashboard-anggota/{member_id}")
    assert response.status_code == 200
    assert name in response.text
    assert "Sentimen pemberitaan media online" in response.text
    assert "Publikasi &amp; dokumentasi Humas" in response.text
    assert "Tugas &amp; fungsi dewan" in response.text


def test_member_role_only_sees_own_dashboard(seeded_client):
    test_client, _ = seeded_client
    own_id, _ = _member()
    other_id, _ = _member("II")
    _create_member_account(own_id)

    login(test_client, "ujianggota", "Anggota#Uji2026")

    response = test_client.get("/", follow_redirects=False)
    assert response.status_code in (302, 303)
    assert response.headers["location"].endswith(f"/dashboard-anggota/{own_id}")

    response = test_client.get(f"/dashboard-anggota/{own_id}")
    assert response.status_code == 200

    response = test_client.get(f"/dashboard-anggota/{other_id}")
    assert response.status_code == 403


def test_staff_sentiment_scope_and_search(seeded_client, monkeypatch):
    from app.services import tavily

    test_client, _ = seeded_client
    own_id, _ = _member("I")
    other_id, _ = _member("II")

    login(test_client, "komisi1", "Komisi1#Riau2026")

    response = test_client.get("/sentimen")
    assert response.status_code == 200

    response = test_client.get(f"/dashboard-anggota/{other_id}")
    assert response.status_code == 200

    token = get_csrf(test_client)
    response = test_client.post(
        f"/anggota/{other_id}/sentimen/cari",
        data={"csrf_token": token},
        follow_redirects=False,
    )
    assert response.status_code == 403

    monkeypatch.setattr(
        tavily,
        "search_news",
        lambda *args, **kwargs: [
            {
                "title": "Anggota DPRD Riau diapresiasi warga",
                "url": "https://contoh.test/berita-uji",
                "source": "contoh.test",
                "snippet": "Kinerja baik dan responsif terhadap aspirasi masyarakat.",
                "published_at": None,
            }
        ],
    )
    response = test_client.post(
        f"/anggota/{own_id}/sentimen/cari",
        data={"csrf_token": token},
        follow_redirects=False,
    )
    assert response.status_code in (302, 303)

    response = test_client.get(f"/anggota/{own_id}/sentimen")
    assert response.status_code == 200
    assert "Anggota DPRD Riau diapresiasi warga" in response.text
    assert "Positif" in response.text


def test_sentiment_list_filters_by_tone(seeded_client, monkeypatch):
    from app.services import tavily

    test_client, _ = seeded_client
    member_id, _ = _member("I")
    login(test_client, "komisi1", "Komisi1#Riau2026")
    token = get_csrf(test_client)

    monkeypatch.setattr(
        tavily,
        "search_news",
        lambda *args, **kwargs: [
            {
                "title": "Kinerja anggota dinilai memuaskan",
                "url": "https://contoh.test/positif",
                "source": "contoh.test",
                "snippet": "Warga mengapresiasi kinerja baik anggota dewan.",
                "published_at": None,
            },
            {
                "title": "Anggota dikritik karena tidak hadir",
                "url": "https://contoh.test/negatif",
                "source": "contoh.test",
                "snippet": "Sejumlah warga kecewa dan mengecewakan.",
                "published_at": None,
            },
        ],
    )
    test_client.post(
        f"/anggota/{member_id}/sentimen/cari",
        data={"csrf_token": token},
        follow_redirects=False,
    )

    response = test_client.get(f"/anggota/{member_id}/sentimen?tone=negatif")
    assert response.status_code == 200
    assert "Anggota dikritik karena tidak hadir" in response.text
    assert "Kinerja anggota dinilai memuaskan" not in response.text
