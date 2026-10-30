"""Pengujian seleksi foto AI: kunci, kuota, skill berbagi, dan pembelajaran."""

from __future__ import annotations

import io
import re
from datetime import date

from PIL import Image

from tests.conftest import login


def _csrf(client, path: str = "/seleksi-foto") -> str:
    response = client.get(path)
    assert response.status_code == 200, response.text
    match = re.search(r'name="csrf_token" value="([^"]+)"', response.text)
    assert match, "Token CSRF tidak ditemukan"
    return match.group(1)


def _jpeg(color=(120, 90, 150)) -> bytes:
    image = Image.new("RGB", (640, 480), color)
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=88)
    return buffer.getvalue()


def _user(db, username: str, role: str = "humas"):
    from app.models import User
    from app.security import hash_password

    user = User(
        username=username,
        full_name=f"Pengguna {username}",
        password_hash=hash_password("Riau#Test2026"),
        role=role,
        is_active=True,
    )
    db.add(user)
    db.flush()
    return user


def _settings(db, user, *, key: str = "AIzaTestKey1234567890", rpd: int = 500):
    from app.services import photo_curator
    from app.services.keyvault import encrypt_secret, key_hint

    row = photo_curator.get_settings_row(db, user.id, create=True)
    row.api_key_encrypted = encrypt_secret(key)
    row.api_key_hint = key_hint(key)
    row.rpm = 15
    row.tpm = 250_000
    row.rpd = rpd
    db.flush()
    return row


def _activity(db, user):
    from app.models import Activity
    from app.constants import STATUS_DRAFT

    row = Activity(
        code="KEG-TEST-PS",
        title="Rapat Kerja Uji Seleksi Foto",
        category="Rapat",
        status=STATUS_DRAFT,
        activity_date=date.today(),
        location_name="Ruang Rapat",
        created_by_id=user.id,
    )
    db.add(row)
    db.flush()
    return row


def _run_with_photos(db, user, *, total: int = 2, rpd: int = 500, target: int = 0):
    from app.constants import SELECTION_QUEUED
    from app.models import PhotoSelectionItem, PhotoSelectionRun
    from app.services import photo_curator

    _settings(db, user, rpd=rpd)
    run = PhotoSelectionRun(
        user_id=user.id,
        skill_key="jurnalistik",
        skill_name="Jurnalistik & Momen",
        skill_instructions="Utamakan momen penting.",
        model="gemini-3.5-flash-lite",
        status=SELECTION_QUEUED,
        target_count=target,
        min_score=60,
        total_items=total,
    )
    db.add(run)
    db.flush()
    colors = [(120, 80, 140), (30, 120, 160), (160, 110, 40), (60, 150, 80)]
    for index in range(1, total + 1):
        prepared = photo_curator.save_selection_photo(_jpeg(colors[index % len(colors)]))
        db.add(
            PhotoSelectionItem(
                run_id=run.id,
                position=index,
                original_name=f"foto-{index}.jpg",
                **prepared,
            )
        )
    db.commit()
    db.refresh(run)
    return run


def test_key_is_encrypted_and_never_rendered(client):
    test_client, _ = client
    login(test_client, "superadmin", "Super#Test2026")
    token = _csrf(test_client)
    key = "AIzaSuperSecretKey99887766"
    response = test_client.post(
        "/seleksi-foto/pengaturan",
        data={
            "csrf_token": token,
            "api_key": key,
            "model": "gemini-3.5-flash-lite",
            "rpm": "15",
            "tpm": "250000",
            "rpd": "500",
            "preferred_notes": "Utamakan wajah pimpinan.",
            "default_skill_key": "jurnalistik",
            "auto_learn": "1",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

    from app.database import SessionLocal
    from app.models import AiPhotoSettings
    from app.services.keyvault import decrypt_secret

    db = SessionLocal()
    try:
        row = (
            db.query(AiPhotoSettings)
            .filter(AiPhotoSettings.user_id == 1)
            .one_or_none()
        )
        if row is None:
            row = db.query(AiPhotoSettings).one()
        assert row.api_key_encrypted
        assert key not in row.api_key_encrypted
        assert decrypt_secret(row.api_key_encrypted) == key
        assert row.api_key_hint.endswith(key[-4:])
        assert row.tpm == 250_000
    finally:
        db.close()

    page = test_client.get("/seleksi-foto/pengaturan")
    assert page.status_code == 200
    assert key not in page.text
    assert "250K TPM" in page.text


def test_keyvault_rejects_tampering(client):
    from app.services.keyvault import KeyVaultError, decrypt_secret, encrypt_secret

    token = encrypt_secret("AIzaContohKunciPanjang123")
    tampered = token[:-2] + ("AA" if token[-2:] != "AA" else "BB")
    try:
        decrypt_secret(tampered)
    except KeyVaultError:
        pass
    else:  # pragma: no cover - pertahanan
        raise AssertionError("Token yang diubah seharusnya ditolak")


def test_usage_snapshot_counts_tpm_and_daily_tokens(client):
    from app.database import SessionLocal
    from app.models import AiRequestLog
    from app.services import photo_curator

    db = SessionLocal()
    try:
        user = _user(db, "kuota-user")
        db.add_all(
            [
                AiRequestLog(
                    user_id=user.id,
                    model="gemini-3.5-flash-lite",
                    status="ok",
                    total_tokens=1200,
                    prompt_tokens=900,
                    output_tokens=300,
                ),
                AiRequestLog(
                    user_id=user.id,
                    model="gemini-3.5-flash-lite",
                    status="ok",
                    total_tokens=800,
                    prompt_tokens=600,
                    output_tokens=200,
                ),
            ]
        )
        db.commit()
        usage = photo_curator.usage_snapshot(db, user.id, 15, 500, 250000)
        assert usage["rpm_used"] == 2
        assert usage["tpm_used"] == 2000
        assert usage["tpm_remaining"] == 248000
        assert usage["tokens_today"] == 2000
        assert usage["rpd_remaining"] == 498
    finally:
        db.close()


def test_shared_skills_are_sorted_and_can_be_cloned(client):
    test_client, _ = client
    login(test_client, "superadmin", "Super#Test2026")

    from app.database import SessionLocal
    from app.models import PhotoSelectionSkill, User

    db = SessionLocal()
    try:
        owner = _user(db, "pemilik-skill")
        low = PhotoSelectionSkill(
            user_id=owner.id,
            name="Skill Jarang Dipakai",
            description="Preset lama",
            instructions="Pilih foto biasa.",
            is_shared=True,
            share_usage_count=1,
        )
        high = PhotoSelectionSkill(
            user_id=owner.id,
            name="Skill Paling Populer",
            description="Preset favorit tim",
            instructions="Pilih foto pimpinan.",
            is_shared=True,
            share_usage_count=9,
        )
        private = PhotoSelectionSkill(
            user_id=owner.id,
            name="Skill Privat",
            description="Tidak dibagikan",
            instructions="Jangan tampil.",
            is_shared=False,
        )
        db.add_all([low, high, private])
        db.commit()
        high_id = high.id
        low_id = low.id
    finally:
        db.close()

    page = test_client.get("/seleksi-foto/skill")
    assert page.status_code == 200
    html = page.text
    assert "Skill Paling Populer" in html
    assert "Skill Jarang Dipakai" in html
    assert "Skill Privat" not in html
    assert html.index("Skill Paling Populer") < html.index("Skill Jarang Dipakai")
    assert "9×" in html

    token = _csrf(test_client)
    response = test_client.post(
        f"/seleksi-foto/skill/{high_id}/salin",
        data={"csrf_token": token},
        follow_redirects=False,
    )
    assert response.status_code == 303

    db = SessionLocal()
    try:
        viewer = db.query(User).filter(User.username == "superadmin").one()
        clone = (
            db.query(PhotoSelectionSkill)
            .filter(
                PhotoSelectionSkill.user_id == viewer.id,
                PhotoSelectionSkill.name.like("Skill Paling Populer%"),
            )
            .one()
        )
        assert clone.instructions == "Pilih foto pimpinan."
        assert clone.is_shared is False
        assert clone.auto_update is True
        # Skill milik orang lain tetap utuh.
        source = db.get(PhotoSelectionSkill, high_id)
        assert source.share_usage_count == 9
    finally:
        db.close()


def test_starting_with_shared_skill_counts_usage(client, monkeypatch):
    test_client, _ = client
    login(test_client, "superadmin", "Super#Test2026")

    from app.database import SessionLocal
    from app.models import PhotoSelectionSkill, User
    from app.services import photo_curator

    db = SessionLocal()
    try:
        owner = _user(db, "pemilik-berbagi")
        shared = PhotoSelectionSkill(
            user_id=owner.id,
            name="Skill Bersama",
            description="Dipakai bersama",
            instructions="Utamakan foto bersama.",
            is_shared=True,
            target_count=0,
            min_score=60,
        )
        db.add(shared)
        db.flush()
        shared_id = shared.id
        superadmin = db.query(User).filter(User.username == "superadmin").one()
        _settings(db, superadmin)
        db.commit()
    finally:
        db.close()

    monkeypatch.setattr(photo_curator, "enqueue_run", lambda run_id: None)
    token = _csrf(test_client)
    response = test_client.post(
        "/seleksi-foto/mulai",
        data={
            "csrf_token": token,
            "skill_key": f"shared:{shared_id}",
            "target_count": "0",
            "min_score": "60",
            "notes": "Foto bersama pimpinan.",
            "activity_id": "0",
        },
        files={"photos": ("rapat.jpg", _jpeg(), "image/jpeg")},
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text

    db = SessionLocal()
    try:
        row = db.get(PhotoSelectionSkill, shared_id)
        assert row.share_usage_count == 1
    finally:
        db.close()


def test_process_run_pauses_at_rpd_and_resumes(client, monkeypatch):
    from app.database import SessionLocal
    from app.constants import SELECTION_DONE, SELECTION_PAUSED
    from app.models import PhotoSelectionItem, PhotoSelectionRun, User
    from app.services import photo_curator

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == "superadmin").one()
        run = _run_with_photos(db, user, total=2, rpd=1)

        def fake_analyze(api_key, model, run_row, item, technical, *, duplicate, usage_sink=None):
            assert api_key
            if usage_sink is not None:
                usage_sink.update(
                    {
                        "promptTokenCount": 1000,
                        "candidatesTokenCount": 200,
                        "totalTokenCount": 1200,
                    }
                )
            return {
                "score": 80,
                "verdict": "selected",
                "reason": "Momen jelas dan tajam.",
                "caption": "Rapat kerja berlangsung",
                "tags": ["rapat", "pimpinan"],
                "strengths": ["wajah jelas"],
                "weaknesses": [],
                "face_count": 2,
                "sharpness": 80,
                "exposure": 75,
                "composition": 78,
                "relevance": 82,
            }

        monkeypatch.setattr(photo_curator, "_analyze_with_gemini", fake_analyze)
        photo_curator.process_run(run.id)
        db.expire_all()
        run = db.get(PhotoSelectionRun, run.id)
        assert run.status == SELECTION_PAUSED
        assert run.processed_items == 1
        assert run.quota_used == 1
        assert run.tokens_used == 1200
        pending = (
            db.query(PhotoSelectionItem)
            .filter(
                PhotoSelectionItem.run_id == run.id,
                PhotoSelectionItem.verdict == "pending",
            )
            .count()
        )
        assert pending == 1

        run.rpd = 10
        run.status = "queued"
        run.error = None
        db.commit()
        photo_curator.process_run(run.id)
        db.expire_all()
        run = db.get(PhotoSelectionRun, run.id)
        assert run.status == SELECTION_DONE
        assert run.selected_count == 2
    finally:
        db.close()


def test_learning_updates_skill_and_global_preferences(client):
    from app.database import SessionLocal
    from app.constants import SELECTION_DONE
    from app.models import PhotoSelectionItem, PhotoSelectionRun, User
    from app.services import photo_curator

    db = SessionLocal()
    try:
        user = _user(db, "pelajar-skill")
        settings_row = _settings(db, user)
        skill = photo_curator.PhotoSelectionSkill(
            user_id=user.id,
            name="Skill Adaptif Uji",
            instructions="Pilih foto rapat.",
            min_score=70,
            target_count=3,
            auto_update=True,
        )
        db.add(skill)
        db.flush()
        run = PhotoSelectionRun(
            user_id=user.id,
            skill_key=f"custom:{skill.id}",
            skill_name=skill.name,
            skill_instructions=skill.instructions,
            model="gemini-3.5-flash-lite",
            status=SELECTION_DONE,
            target_count=3,
            min_score=70,
            total_items=2,
            selected_count=5,
            processed_items=2,
        )
        db.add(run)
        db.flush()
        selected = PhotoSelectionItem(
            run_id=run.id,
            position=1,
            original_name="a.jpg",
            verdict="selected",
            ai_verdict="backup",
            manual_override=True,
            score=84,
            tags=["pimpinan", "rapat"],
            strengths=["wajah jelas"],
            weaknesses=[],
        )
        rejected = PhotoSelectionItem(
            run_id=run.id,
            position=2,
            original_name="b.jpg",
            verdict="rejected",
            ai_verdict="selected",
            manual_override=True,
            score=42,
            tags=["punggung", "blur"],
            strengths=[],
            weaknesses=["wajah tertutup"],
        )
        db.add_all([selected, rejected])
        db.commit()
        db.refresh(run)
        db.refresh(skill)

        result = photo_curator.learn_from_run(db, run)
        db.commit()
        db.refresh(skill)
        db.refresh(settings_row)

        assert result["updated"] is True
        assert "Utamakan" in skill.learned_preferences
        assert "Hindari" in skill.learned_preferences
        assert skill.min_score < 70
        assert skill.target_count == 5
        assert settings_row.learned_preferences
        assert skill.auto_updated_at is not None
    finally:
        db.close()


def test_apply_selection_copies_photos_to_activity(client, monkeypatch):
    test_client, _ = client
    login(test_client, "superadmin", "Super#Test2026")

    from app.database import SessionLocal
    from app.models import ActivityPhoto, PhotoSelectionItem, PhotoSelectionRun, User
    from app.services import jobs

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == "superadmin").one()
        run = _run_with_photos(db, user, total=1)
        run.status = "done"
        item = (
            db.query(PhotoSelectionItem)
            .filter(PhotoSelectionItem.run_id == run.id)
            .one()
        )
        item.verdict = "selected"
        activity = _activity(db, user)
        db.commit()
        run_id = run.id
        activity_id = activity.id
    finally:
        db.close()

    monkeypatch.setattr(jobs, "enqueue_photo", lambda photo_id: None)
    token = _csrf(test_client)
    response = test_client.post(
        f"/seleksi-foto/sesi/{run_id}/terapkan",
        data={"csrf_token": token, "activity_id": activity_id},
        follow_redirects=False,
    )
    assert response.status_code == 303, response.text
    assert f"/kegiatan/{activity_id}" in response.headers["location"]

    db = SessionLocal()
    try:
        assert (
            db.query(ActivityPhoto)
            .filter(ActivityPhoto.activity_id == activity_id)
            .count()
            == 1
        )
        item = (
            db.query(PhotoSelectionItem)
            .filter(PhotoSelectionItem.run_id == run_id)
            .one()
        )
        assert item.applied_photo_id is not None
        run = db.get(PhotoSelectionRun, run_id)
        assert run.applied_count == 1
    finally:
        db.close()


def test_selection_access_is_limited_to_content_roles(client):
    test_client, _ = client
    login(test_client, "superadmin", "Super#Test2026")

    from app.database import SessionLocal
    from app.models import User
    from app.security import hash_password

    db = SessionLocal()
    try:
        db.add(
            User(
                username="staf-uji",
                full_name="Staf Komisi Uji",
                password_hash=hash_password("Riau#Test2026"),
                role="staf_komisi",
                is_active=True,
            )
        )
        db.commit()
    finally:
        db.close()

    token = _csrf(test_client)
    test_client.post("/logout", data={"csrf_token": token}, follow_redirects=False)
    login(test_client, "staf-uji", "Riau#Test2026")
    response = test_client.get("/seleksi-foto")
    assert response.status_code == 403
