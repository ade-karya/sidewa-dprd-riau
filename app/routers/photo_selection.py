"""Ruang kerja seleksi foto Humas berbasis Gemini.

Fitur ini memakai kunci API milik masing-masing pengguna, menghormati batas
RPM/RPD kunci tersebut, dan menyimpan riwayat sesi kurasi. Pengguna dapat
memilih skill bawaan atau membuat skill sesuai preferensi mereka.
"""

from __future__ import annotations

import math
import mimetypes
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..audit import audit
from ..config import settings
from ..constants import (
    ADMIN_ROLES,
    CONTENT_MANAGER_ROLES,
    SELECTION_BACKUP,
    SELECTION_CANCELLED,
    SELECTION_DONE,
    SELECTION_FAILED,
    SELECTION_FAILED_ITEM,
    SELECTION_PAUSED,
    SELECTION_PENDING,
    SELECTION_QUEUED,
    SELECTION_REJECTED,
    SELECTION_RUNNING,
    SELECTION_SELECTED,
    SELECTION_STATUS_LABELS,
    SELECTION_STATUS_TONES,
    SELECTION_VERDICT_LABELS,
    SELECTION_VERDICT_TONES,
)
from ..database import get_db
from ..deps import csrf_protect, flash, require_roles
from ..models import (
    Activity,
    ActivityPhoto,
    PhotoSelectionItem,
    PhotoSelectionRun,
    PhotoSelectionSkill,
    User,
    utcnow,
)
from ..services import jobs, photo_curator
from ..services.analytics import dashboard_stats
from ..services.images import ImageValidationError, delete_paths, save_image
from ..services.keyvault import KeyVaultError, encrypt_secret, key_hint
from ..templating import render

router = APIRouter(dependencies=[Depends(csrf_protect)])

ACCESS = require_roles(*CONTENT_MANAGER_ROLES)

TERMINAL_STATUSES = {SELECTION_DONE, SELECTION_FAILED, SELECTION_CANCELLED}

DOWNLOAD_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


def _photo_download_name(item: PhotoSelectionItem, path: Path) -> str:
    """Nama berkas ramah pengguna; tetap berekstensi foto asli."""
    label = item.caption or item.original_name or f"foto-{item.position}"
    label = Path(label).stem
    label = re.sub(r'[\\/:*?"<>|\r\n]+', "-", label).strip(" .-_")
    if not label:
        label = f"foto-{item.position}"
    return f"{label[:90]}{path.suffix or '.jpg'}"


def _usage_context(db: Session, user: User, row) -> dict[str, Any]:
    rpm = row.rpm if row else settings.photo_selection_rpm_default
    rpd = row.rpd if row else settings.photo_selection_rpd_default
    tpm = row.tpm if row else settings.photo_selection_tpm_default
    return photo_curator.usage_snapshot(db, user.id, rpm, rpd, tpm)


def _recent_runs(db: Session, user: User, limit: int = 8) -> list[PhotoSelectionRun]:
    return (
        db.query(PhotoSelectionRun)
        .filter(PhotoSelectionRun.user_id == user.id)
        .order_by(PhotoSelectionRun.created_at.desc(), PhotoSelectionRun.id.desc())
        .limit(limit)
        .all()
    )


def _activity_choices(db: Session) -> list[Activity]:
    return (
        db.query(Activity)
        .order_by(Activity.activity_date.desc(), Activity.id.desc())
        .limit(60)
        .all()
    )


def _own_run_or_404(db: Session, run_id: int, user: User) -> PhotoSelectionRun:
    run = db.get(PhotoSelectionRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Sesi seleksi foto tidak ditemukan.")
    if run.user_id != user.id and user.role not in ADMIN_ROLES:
        raise HTTPException(
            status_code=403, detail="Anda hanya dapat membuka sesi seleksi foto milik sendiri."
        )
    return run


def _status_payload(run: PhotoSelectionRun) -> dict[str, Any]:
    wait_seconds = 0
    if run.next_request_at:
        wait_seconds = max(
            0, math.ceil((run.next_request_at - utcnow()).total_seconds())
        )
    return {
        "id": run.id,
        "status": run.status,
        "status_label": SELECTION_STATUS_LABELS.get(run.status, run.status),
        "terminal": run.status in TERMINAL_STATUSES,
        "wait_seconds": wait_seconds,
        "error": run.error,
        "target_count": run.target_count,
        "min_score": run.min_score,
        "total": run.total_items,
        "processed": run.processed_items,
        "selected": run.selected_count,
        "backup": run.backup_count,
        "rejected": run.rejected_count,
        "failed": run.failed_count,
        "quota_used": run.quota_used,
        "tokens_used": run.tokens_used,
        "progress": round(
            (run.processed_items / run.total_items * 100) if run.total_items else 0
        ),
        "items": [
            {
                "id": item.id,
                "verdict": item.verdict,
                "verdict_label": SELECTION_VERDICT_LABELS.get(
                    item.verdict, item.verdict
                ),
                "score": item.score,
                "reason": item.reason,
                "error": item.error,
            }
            for item in run.items
        ],
    }


def _selection_page(
    request: Request,
    user: User,
    db: Session,
    view: str = "dashboard",
) -> Any:
    row = photo_curator.get_settings_row(db, user.id)
    row_default = row.default_skill_key if row else ""
    skills = photo_curator.skill_options(db, user)
    if not row_default or row_default not in {skill["key"] for skill in skills}:
        row_default = skills[0]["key"] if skills else ""
    runs = _recent_runs(db, user)
    total_selected = sum(run.selected_count for run in runs)
    total_quota = sum(run.quota_used for run in runs)
    selection_state = {
        "has_key": bool(row and row.api_key_encrypted),
        "key_hint": row.api_key_hint if row else "",
        "key_verified_at": row.key_verified_at if row else None,
        "key_error": row.key_error if row else None,
        "model": row.model if row else settings.photo_selection_model,
        "rpm": row.rpm if row else settings.photo_selection_rpm_default,
        "rpd": row.rpd if row else settings.photo_selection_rpd_default,
        "tpm": row.tpm if row else settings.photo_selection_tpm_default,
        "preferred_notes": row.preferred_notes if row else "",
        "auto_learn": row.auto_learn if row else True,
        "learned_preferences": row.learned_preferences if row else "",
        "learned_updated_at": row.learned_updated_at if row else None,
    }
    return render(
        request,
        "photo_selection/index.html",
        user=user,
        selection=selection_state,
        usage=_usage_context(db, user, row),
        skills=skills,
        default_skill_key=row_default,
        runs=runs,
        activities=_activity_choices(db),
        max_photos=settings.photo_selection_max_photos,
        total_selected=total_selected,
        total_quota=total_quota,
        default_model=settings.photo_selection_model,
        stats=dashboard_stats(db, user),
        view=view,
    )


@router.get("/seleksi-foto")
def selection_dashboard(
    request: Request,
    user: User = Depends(ACCESS),
    db: Session = Depends(get_db),
):
    return _selection_page(request, user, db, "dashboard")


@router.get("/seleksi-foto/pengaturan")
def selection_settings(
    request: Request,
    user: User = Depends(ACCESS),
    db: Session = Depends(get_db),
):
    return _selection_page(request, user, db, "settings")


@router.get("/seleksi-foto/skill")
def selection_skills(
    request: Request,
    user: User = Depends(ACCESS),
    db: Session = Depends(get_db),
):
    return _selection_page(request, user, db, "skills")


@router.get("/seleksi-foto/mulai")
def selection_start(
    request: Request,
    user: User = Depends(ACCESS),
    db: Session = Depends(get_db),
):
    return _selection_page(request, user, db, "start")


@router.get("/seleksi-foto/riwayat")
def selection_history(
    request: Request,
    user: User = Depends(ACCESS),
    db: Session = Depends(get_db),
):
    return _selection_page(request, user, db, "history")


@router.post("/seleksi-foto/pengaturan")
def save_settings(
    request: Request,
    api_key: str = Form(""),
    model: str = Form(""),
    rpm: int = Form(15),
    rpd: int = Form(500),
    tpm: int = Form(250000),
    preferred_notes: str = Form(""),
    default_skill_key: str = Form("jurnalistik"),
    auto_learn: str = Form(""),
    learned_preferences: str = Form(""),
    user: User = Depends(ACCESS),
    db: Session = Depends(get_db),
):
    row = photo_curator.get_settings_row(db, user.id, create=True)
    api_key = api_key.strip()
    if api_key:
        if len(api_key) < 10 or len(api_key) > 300 or re.search(r"\s", api_key):
            flash(request, "Format kunci API tidak valid. Salin ulang dari Google AI Studio.", "danger")
            return RedirectResponse("/seleksi-foto/pengaturan", status_code=303)
        try:
            row.api_key_encrypted = encrypt_secret(api_key)
        except KeyVaultError as exc:
            flash(request, str(exc), "danger")
            return RedirectResponse("/seleksi-foto/pengaturan", status_code=303)
        row.api_key_hint = key_hint(api_key)
        row.key_verified_at = None
        row.key_error = None
    row.model = (model.strip() or settings.photo_selection_model)[:80]
    row.rpm = max(1, min(300, rpm))
    row.rpd = max(1, min(10000, rpd))
    row.tpm = max(1000, min(2_000_000, tpm))
    row.preferred_notes = preferred_notes.strip()[:1200]
    row.auto_learn = auto_learn.strip().lower() in {"1", "true", "on", "yes"}
    row.learned_preferences = learned_preferences.strip()[:1200]
    try:
        skill = photo_curator.resolve_skill(db, user, default_skill_key)
    except photo_curator.SelectionError:
        skill = photo_curator.builtin_skill("jurnalistik")
    row.default_skill_key = skill["key"]
    row.is_active = True
    audit(
        db,
        request,
        "AI_KEY_SAVE",
        actor=user,
        entity_type="ai_photo_settings",
        entity_id=row.id,
        summary="Memperbarui pengaturan seleksi foto AI",
        detail={
            "model": row.model,
            "rpm": row.rpm,
            "rpd": row.rpd,
            "tpm": row.tpm,
            "key_changed": bool(api_key),
            "auto_learn": row.auto_learn,
        },
    )
    db.commit()
    flash(
        request,
        "Pengaturan seleksi foto disimpan."
        + (" Kunci API baru tersimpan terenkripsi." if api_key else ""),
        "success",
    )
    return RedirectResponse("/seleksi-foto/pengaturan", status_code=303)


@router.post("/seleksi-foto/pengaturan/uji")
def test_key(
    request: Request,
    user: User = Depends(ACCESS),
    db: Session = Depends(get_db),
):
    row = photo_curator.get_settings_row(db, user.id)
    try:
        api_key = photo_curator.api_key_for(row)
    except photo_curator.SelectionError as exc:
        flash(request, str(exc), "danger")
        return RedirectResponse("/seleksi-foto/pengaturan", status_code=303)
    ok, message = photo_curator.verify_api_key(api_key, row.model)
    if ok:
        row.key_verified_at = utcnow()
        row.key_error = None
    else:
        row.key_error = message[:500]
    audit(
        db,
        request,
        "AI_KEY_TEST",
        actor=user,
        entity_type="ai_photo_settings",
        entity_id=row.id,
        summary="Menguji kunci API seleksi foto",
        detail={"ok": ok},
    )
    db.commit()
    flash(request, message, "success" if ok else "danger")
    return RedirectResponse("/seleksi-foto/pengaturan", status_code=303)


@router.post("/seleksi-foto/pengaturan/hapus-kunci")
def delete_key(
    request: Request,
    user: User = Depends(ACCESS),
    db: Session = Depends(get_db),
):
    row = photo_curator.get_settings_row(db, user.id)
    if not row or not row.api_key_encrypted:
        flash(request, "Belum ada kunci API yang tersimpan.", "warning")
        return RedirectResponse("/seleksi-foto/pengaturan", status_code=303)
    row.api_key_encrypted = ""
    row.api_key_hint = ""
    row.key_verified_at = None
    row.key_error = None
    audit(
        db,
        request,
        "AI_KEY_DELETE",
        actor=user,
        entity_type="ai_photo_settings",
        entity_id=row.id,
        summary="Menghapus kunci API seleksi foto",
    )
    db.commit()
    flash(request, "Kunci API dihapus. Unggah kunci baru untuk memakai seleksi foto AI.", "success")
    return RedirectResponse("/seleksi-foto/pengaturan", status_code=303)


@router.post("/seleksi-foto/skill")
def save_skill(
    request: Request,
    skill_id: str = Form(""),
    name: str = Form(""),
    description: str = Form(""),
    instructions: str = Form(""),
    target_count: str = Form("0"),
    min_score: str = Form("60"),
    auto_update: str = Form(""),
    is_shared: str = Form(""),
    user: User = Depends(ACCESS),
    db: Session = Depends(get_db),
):
    name = name.strip()[:80]
    if len(name) < 3:
        flash(request, "Nama skill minimal 3 karakter.", "danger")
        return RedirectResponse("/seleksi-foto/skill", status_code=303)
    try:
        target = max(0, min(100, int(target_count or 0)))
        threshold = max(0, min(100, int(min_score or 60)))
    except ValueError:
        flash(request, "Target dan ambang skor harus berupa angka.", "danger")
        return RedirectResponse("/seleksi-foto/skill", status_code=303)
    row = None
    if skill_id.strip():
        try:
            row = (
                db.query(PhotoSelectionSkill)
                .filter(
                    PhotoSelectionSkill.id == int(skill_id),
                    PhotoSelectionSkill.user_id == user.id,
                )
                .first()
            )
        except ValueError:
            row = None
        if not row:
            flash(request, "Skill tidak ditemukan.", "danger")
            return RedirectResponse("/seleksi-foto/skill", status_code=303)
    if row is None:
        row = PhotoSelectionSkill(user_id=user.id)
        db.add(row)
    row.name = name
    row.description = description.strip()[:220]
    row.instructions = instructions.strip()[:2000]
    row.target_count = target
    row.min_score = threshold
    row.auto_update = auto_update.strip().lower() in {"1", "true", "on", "yes"}
    row.is_shared = is_shared.strip().lower() in {"1", "true", "on", "yes"}
    row.is_active = True
    try:
        db.flush()
        audit(
            db,
            request,
            "AI_SKILL_SAVE",
            actor=user,
            entity_type="photo_selection_skill",
            entity_id=row.id,
            summary=f"Menyimpan skill seleksi foto '{row.name}'",
            detail={"shared": row.is_shared, "auto_update": row.auto_update},
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        flash(request, "Nama skill sudah dipakai. Gunakan nama lain.", "danger")
        return RedirectResponse("/seleksi-foto/skill", status_code=303)
    flash(request, f"Skill '{row.name}' disimpan.", "success")
    return RedirectResponse("/seleksi-foto/skill", status_code=303)


@router.post("/seleksi-foto/skill/{skill_id}/salin")
def clone_shared_skill(
    skill_id: int,
    request: Request,
    user: User = Depends(ACCESS),
    db: Session = Depends(get_db),
):
    source = (
        db.query(PhotoSelectionSkill)
        .filter(
            PhotoSelectionSkill.id == skill_id,
            PhotoSelectionSkill.user_id != user.id,
            PhotoSelectionSkill.is_shared.is_(True),
            PhotoSelectionSkill.is_active.is_(True),
        )
        .first()
    )
    if not source:
        flash(request, "Skill komunitas tidak ditemukan atau sudah tidak dibagikan.", "warning")
        return RedirectResponse("/seleksi-foto/skill", status_code=303)
    base_name = f"{source.name} (salinan)"[:74]
    name = base_name
    suffix = 2
    while (
        db.query(PhotoSelectionSkill)
        .filter(
            PhotoSelectionSkill.user_id == user.id,
            PhotoSelectionSkill.name == name,
        )
        .first()
    ):
        name = f"{base_name} {suffix}"[:80]
        suffix += 1
    row = PhotoSelectionSkill(
        user_id=user.id,
        name=name,
        icon=source.icon or "sparkles",
        description=source.description,
        instructions=source.instructions,
        target_count=source.target_count,
        min_score=source.min_score,
        auto_update=True,
        learned_preferences=source.learned_preferences,
        is_shared=False,
    )
    db.add(row)
    db.flush()
    audit(
        db,
        request,
        "AI_SKILL_SAVE",
        actor=user,
        entity_type="photo_selection_skill",
        entity_id=row.id,
        summary=f"Menyalin skill komunitas '{source.name}'",
        detail={"source_skill_id": source.id},
    )
    db.commit()
    flash(
        request,
        f"Skill '{source.name}' disalin ke skill saya. Anda dapat menyesuaikannya sendiri.",
        "success",
    )
    return RedirectResponse("/seleksi-foto/skill", status_code=303)


@router.post("/seleksi-foto/skill/{skill_id}/hapus")
def delete_skill(
    skill_id: int,
    request: Request,
    user: User = Depends(ACCESS),
    db: Session = Depends(get_db),
):
    row = (
        db.query(PhotoSelectionSkill)
        .filter(
            PhotoSelectionSkill.id == skill_id,
            PhotoSelectionSkill.user_id == user.id,
        )
        .first()
    )
    if not row:
        flash(request, "Skill tidak ditemukan.", "danger")
        return RedirectResponse("/seleksi-foto/skill", status_code=303)
    settings_row = photo_curator.get_settings_row(db, user.id)
    if settings_row and settings_row.default_skill_key == f"custom:{row.id}":
        settings_row.default_skill_key = "jurnalistik"
    audit(
        db,
        request,
        "AI_SKILL_DELETE",
        actor=user,
        entity_type="photo_selection_skill",
        entity_id=row.id,
        summary=f"Menghapus skill seleksi foto '{row.name}'",
    )
    db.delete(row)
    db.commit()
    flash(request, "Skill dihapus. Sesi lama tetap menyimpan salinan instruksinya.", "success")
    return RedirectResponse("/seleksi-foto/skill", status_code=303)


@router.post("/seleksi-foto/skill/{skill_id}/default")
def set_default_skill(
    skill_id: str,
    request: Request,
    user: User = Depends(ACCESS),
    db: Session = Depends(get_db),
):
    key = skill_id
    try:
        skill = photo_curator.resolve_skill(db, user, key)
    except photo_curator.SelectionError:
        flash(request, "Skill tidak ditemukan.", "danger")
        return RedirectResponse("/seleksi-foto/skill", status_code=303)
    row = photo_curator.get_settings_row(db, user.id, create=True)
    row.default_skill_key = skill["key"]
    db.commit()
    flash(request, f"Skill '{skill['name']}' dijadikan pilihan awal.", "success")
    return RedirectResponse("/seleksi-foto/skill", status_code=303)


@router.post("/seleksi-foto/pembelajaran/selaraskan")
def sync_learning(
    request: Request,
    user: User = Depends(ACCESS),
    db: Session = Depends(get_db),
):
    result = photo_curator.refresh_learning(db, user)
    audit(
        db,
        request,
        "AI_SKILL_SAVE",
        actor=user,
        entity_type="ai_photo_settings",
        entity_id=user.id,
        summary="Menyelaraskan preferensi skill dari koreksi pengguna",
        detail={"updated": result["updated"]},
    )
    db.commit()
    if result["updated"]:
        flash(
            request,
            f"{result['updated']} preferensi skill diperbarui dari koreksi dan foto yang Anda terapkan.",
            "success",
        )
    else:
        flash(
            request,
            "Belum ada cukup koreksi manual untuk memperbarui preferensi. Ubah pilihan beberapa foto terlebih dahulu.",
            "warning",
        )
    return RedirectResponse("/seleksi-foto/skill", status_code=303)


@router.post("/seleksi-foto/mulai")
async def start_selection(
    request: Request,
    photos: list[UploadFile] = File(default=[]),
    skill_key: str = Form("jurnalistik"),
    target_count: str = Form("0"),
    min_score: str = Form(""),
    notes: str = Form(""),
    activity_id: int = Form(0),
    user: User = Depends(ACCESS),
    db: Session = Depends(get_db),
):
    row = photo_curator.get_settings_row(db, user.id)
    if not row or not row.api_key_encrypted:
        flash(request, "Atur kunci API Gemini terlebih dahulu sebelum memulai seleksi.", "warning")
        return RedirectResponse("/seleksi-foto/pengaturan", status_code=303)
    try:
        photo_curator.api_key_for(row)
    except photo_curator.SelectionError as exc:
        flash(request, str(exc), "danger")
        return RedirectResponse("/seleksi-foto/pengaturan", status_code=303)
    try:
        skill = photo_curator.resolve_skill(db, user, skill_key)
    except photo_curator.SelectionError as exc:
        flash(request, str(exc), "danger")
        return RedirectResponse("/seleksi-foto/skill", status_code=303)
    if skill.get("shared"):
        shared_row = db.get(PhotoSelectionSkill, skill["id"])
        if shared_row and shared_row.user_id != user.id:
            shared_row.share_usage_count += 1

    files = [upload for upload in photos if upload and upload.filename]
    if not files:
        flash(request, "Pilih minimal satu foto untuk diseleksi.", "warning")
        return RedirectResponse("/seleksi-foto/mulai", status_code=303)
    if len(files) > settings.photo_selection_max_photos:
        flash(
            request,
            f"Maksimal {settings.photo_selection_max_photos} foto per sesi seleksi.",
            "danger",
        )
        return RedirectResponse("/seleksi-foto/mulai", status_code=303)

    try:
        target = max(0, min(len(files), int(target_count or 0)))
        threshold = (
            max(0, min(100, int(min_score)))
            if str(min_score).strip()
            else int(skill.get("min_score") or 60)
        )
    except ValueError:
        flash(request, "Target dan ambang skor harus berupa angka.", "danger")
        return RedirectResponse("/seleksi-foto/mulai", status_code=303)

    activity = None
    if activity_id:
        activity = db.get(Activity, activity_id)
        if not activity:
            flash(request, "Kegiatan konteks tidak ditemukan.", "danger")
            return RedirectResponse("/seleksi-foto/mulai", status_code=303)

    combined_notes = "\n".join(
        part
        for part in ((row.preferred_notes or "").strip(), notes.strip())
        if part
    )
    run = PhotoSelectionRun(
        user_id=user.id,
        skill_key=skill["key"],
        skill_name=skill["name"],
        skill_instructions=skill["instructions"],
        skill_learned_preferences=skill.get("learned_preferences") or "",
        learned_preferences=row.learned_preferences or "",
        user_notes=combined_notes[:1200],
        model=row.model,
        status=SELECTION_QUEUED,
        target_count=target,
        min_score=threshold,
        activity_id=activity.id if activity else None,
        total_items=len(files),
    )
    db.add(run)
    db.flush()
    saved_paths: list[str] = []
    try:
        for index, upload in enumerate(files, start=1):
            raw = await upload.read(settings.max_upload_bytes + 1)
            if len(raw) > settings.max_upload_bytes:
                raise ImageValidationError(
                    f"Foto {upload.filename} melebihi batas {settings.max_upload_mb} MB."
                )
            prepared = photo_curator.save_selection_photo(raw)
            saved_paths.extend(
                [prepared["file_path"], prepared["thumb_path"]]
            )
            db.add(
                PhotoSelectionItem(
                    run_id=run.id,
                    position=index,
                    original_name=(upload.filename or "foto.jpg")[:255],
                    **prepared,
                )
            )
        audit(
            db,
            request,
            "PHOTO_SELECTION_START",
            actor=user,
            entity_type="photo_selection_run",
            entity_id=run.id,
            summary=f"Memulai seleksi {len(files)} foto dengan skill {skill['name']}",
            detail={
                "skill": skill["key"],
                "target": target,
                "min_score": threshold,
                "activity_id": activity.id if activity else None,
            },
        )
        db.commit()
    except (ImageValidationError, ValueError) as exc:
        db.rollback()
        for path in saved_paths:
            delete_paths(path)
        flash(request, str(exc), "danger")
        return RedirectResponse("/seleksi-foto/mulai", status_code=303)
    except Exception:
        db.rollback()
        for path in saved_paths:
            delete_paths(path)
        raise
    photo_curator.enqueue_run(run.id)
    flash(
        request,
        f"Seleksi {len(files)} foto dimulai. Agen akan menghormati batas "
        f"{row.rpm} RPM, {row.tpm:,} TPM, dan {row.rpd} RPD kunci Anda.",
        "success",
    )
    return RedirectResponse(f"/seleksi-foto/sesi/{run.id}", status_code=303)


@router.get("/seleksi-foto/sesi/{run_id}")
def selection_detail(
    run_id: int,
    request: Request,
    user: User = Depends(ACCESS),
    db: Session = Depends(get_db),
):
    run = _own_run_or_404(db, run_id, user)
    row = photo_curator.get_settings_row(db, user.id)
    items = list(run.items)
    pending = len([item for item in items if item.verdict == SELECTION_PENDING])
    wait_seconds = 0
    if run.next_request_at:
        wait_seconds = max(
            0, math.ceil((run.next_request_at - utcnow()).total_seconds())
        )
    return render(
        request,
        "photo_selection/run.html",
        user=user,
        run=run,
        items=items,
        status_labels=SELECTION_STATUS_LABELS,
        status_tones=SELECTION_STATUS_TONES,
        verdict_labels=SELECTION_VERDICT_LABELS,
        verdict_tones=SELECTION_VERDICT_TONES,
        pending_count=pending,
        wait_seconds=wait_seconds,
        activities=_activity_choices(db),
        usage=_usage_context(db, user, row),
        max_photos=settings.max_photos_per_activity,
        can_resume=run.status in {SELECTION_PAUSED, SELECTION_FAILED}
        and pending > 0,
        can_cancel=run.status in {SELECTION_QUEUED, SELECTION_RUNNING, SELECTION_PAUSED},
        stats=dashboard_stats(db, user),
    )


@router.get("/seleksi-foto/sesi/{run_id}/status.json")
def selection_status(
    run_id: int,
    user: User = Depends(ACCESS),
    db: Session = Depends(get_db),
):
    run = _own_run_or_404(db, run_id, user)
    return JSONResponse(_status_payload(run))


@router.post("/seleksi-foto/sesi/{run_id}/pilihan")
async def update_verdicts(
    run_id: int,
    request: Request,
    user: User = Depends(ACCESS),
    db: Session = Depends(get_db),
):
    run = _own_run_or_404(db, run_id, user)
    form = await request.form()
    valid = {SELECTION_SELECTED, SELECTION_BACKUP, SELECTION_REJECTED}
    items = {
        item.id: item
        for item in db.query(PhotoSelectionItem)
        .filter(PhotoSelectionItem.run_id == run.id)
        .all()
    }
    changed = 0
    for key, value in form.multi_items():
        if not key.startswith("verdict_"):
            continue
        try:
            item_id = int(key.split("_", 1)[1])
        except (ValueError, IndexError):
            continue
        item = items.get(item_id)
        verdict = str(value or "").strip()
        if item is None or verdict not in valid:
            continue
        reason = str(form.get(f"reason_{item_id}") or "").strip()[:500]
        if item.verdict != verdict:
            item.verdict = verdict
            item.manual_override = True
            if reason:
                item.manual_reason = reason
            changed += 1
        elif reason and reason != item.manual_reason:
            item.manual_reason = reason
            item.manual_override = True
            changed += 1
    learned = {"updated": False}
    if changed:
        photo_curator.refresh_counts(db, run)
        learned = photo_curator.learn_from_run(db, run)
        audit(
            db,
            request,
            "PHOTO_SELECTION_VERDICT",
            actor=user,
            entity_type="photo_selection_run",
            entity_id=run.id,
            summary=f"Mengubah {changed} pilihan foto pada sesi #{run.id}",
            detail={"learned": bool(learned.get("updated"))},
        )
        db.commit()
    wants_json = request.headers.get("x-requested-with") == "fetch"
    if wants_json:
        return JSONResponse(
            {
                "ok": True,
                "changed": changed,
                "selected": run.selected_count,
                "backup": run.backup_count,
                "rejected": run.rejected_count,
                "learned": bool(learned.get("updated")),
            }
        )
    message = f"{changed} pilihan foto diperbarui." if changed else "Tidak ada perubahan."
    if learned.get("updated"):
        message += " Preferensi skill ikut diperbarui otomatis."
    flash(request, message, "success")
    return RedirectResponse(f"/seleksi-foto/sesi/{run.id}#hasil", status_code=303)


@router.post("/seleksi-foto/sesi/{run_id}/lanjut")
def resume_selection(
    run_id: int,
    request: Request,
    user: User = Depends(ACCESS),
    db: Session = Depends(get_db),
):
    run = _own_run_or_404(db, run_id, user)
    if run.status not in {SELECTION_PAUSED, SELECTION_FAILED}:
        flash(request, "Sesi ini tidak dalam keadaan dapat dilanjutkan.", "warning")
        return RedirectResponse(f"/seleksi-foto/sesi/{run.id}", status_code=303)
    row = photo_curator.get_settings_row(db, user.id)
    try:
        photo_curator.api_key_for(row)
    except photo_curator.SelectionError as exc:
        flash(request, str(exc), "danger")
        return RedirectResponse(f"/seleksi-foto/sesi/{run.id}", status_code=303)
    db.query(PhotoSelectionItem).filter(
        PhotoSelectionItem.run_id == run.id,
        PhotoSelectionItem.verdict == SELECTION_FAILED_ITEM,
    ).update(
        {
            PhotoSelectionItem.verdict: SELECTION_PENDING,
            PhotoSelectionItem.error: None,
        },
        synchronize_session=False,
    )
    run.cancel_requested = False
    run.status = SELECTION_QUEUED
    run.error = None
    run.next_request_at = None
    run.finished_at = None
    audit(
        db,
        request,
        "PHOTO_SELECTION_RESUME",
        actor=user,
        entity_type="photo_selection_run",
        entity_id=run.id,
        summary=f"Melanjutkan seleksi foto sesi #{run.id}",
    )
    db.commit()
    photo_curator.enqueue_run(run.id)
    flash(request, "Sesi seleksi dilanjutkan. Agen akan memproses foto yang tersisa.", "success")
    return RedirectResponse(f"/seleksi-foto/sesi/{run.id}", status_code=303)


@router.post("/seleksi-foto/sesi/{run_id}/batal")
def cancel_selection(
    run_id: int,
    request: Request,
    user: User = Depends(ACCESS),
    db: Session = Depends(get_db),
):
    run = _own_run_or_404(db, run_id, user)
    if run.status in TERMINAL_STATUSES:
        flash(request, "Sesi ini sudah berakhir.", "warning")
        return RedirectResponse(f"/seleksi-foto/sesi/{run.id}", status_code=303)
    run.cancel_requested = True
    if run.status in {SELECTION_QUEUED, SELECTION_PAUSED}:
        run.status = SELECTION_CANCELLED
        run.finished_at = utcnow()
        run.error = "Seleksi dibatalkan oleh pengguna."
    audit(
        db,
        request,
        "PHOTO_SELECTION_CANCEL",
        actor=user,
        entity_type="photo_selection_run",
        entity_id=run.id,
        summary=f"Membatalkan seleksi foto sesi #{run.id}",
    )
    db.commit()
    flash(request, "Seleksi dibatalkan. Foto yang sudah dinilai tetap tersimpan.", "success")
    return RedirectResponse(f"/seleksi-foto/sesi/{run.id}", status_code=303)


@router.post("/seleksi-foto/sesi/{run_id}/terapkan")
def apply_selection(
    run_id: int,
    request: Request,
    activity_id: int = Form(...),
    user: User = Depends(ACCESS),
    db: Session = Depends(get_db),
):
    run = _own_run_or_404(db, run_id, user)
    activity = db.get(Activity, activity_id)
    if not activity:
        flash(request, "Kegiatan tujuan tidak ditemukan.", "danger")
        return RedirectResponse(f"/seleksi-foto/sesi/{run.id}", status_code=303)
    if activity.status == "archived":
        flash(request, "Kegiatan yang diarsipkan tidak dapat menerima foto baru.", "warning")
        return RedirectResponse(f"/seleksi-foto/sesi/{run.id}", status_code=303)
    selected = (
        db.query(PhotoSelectionItem)
        .filter(
            PhotoSelectionItem.run_id == run.id,
            PhotoSelectionItem.verdict == SELECTION_SELECTED,
            PhotoSelectionItem.applied_photo_id.is_(None),
        )
        .order_by(PhotoSelectionItem.position)
        .all()
    )
    if not selected:
        flash(request, "Tidak ada foto terpilih yang belum diterapkan ke kegiatan.", "warning")
        return RedirectResponse(f"/seleksi-foto/sesi/{run.id}#hasil", status_code=303)
    existing = (
        db.query(ActivityPhoto)
        .filter(ActivityPhoto.activity_id == activity.id)
        .count()
    )
    if existing + len(selected) > settings.max_photos_per_activity:
        flash(
            request,
            f"Kegiatan hanya dapat memuat {settings.max_photos_per_activity} foto. "
            f"Tersedia {max(0, settings.max_photos_per_activity - existing)} slot lagi.",
            "danger",
        )
        return RedirectResponse(f"/seleksi-foto/sesi/{run.id}#hasil", status_code=303)
    saved_paths: list[str] = []
    photo_ids: list[int] = []
    try:
        next_order = existing + 1
        for index, item in enumerate(selected):
            if not item.file_path:
                continue
            path = photo_curator.absolute_path(item.file_path)
            if not path.is_file():
                continue
            raw = path.read_bytes()
            rel_main, rel_thumb, width, height = save_image(raw, "activities")
            saved_paths.extend([rel_main, rel_thumb])
            photo = ActivityPhoto(
                activity_id=activity.id,
                file_path=rel_main,
                thumb_path=rel_thumb,
                width=width,
                height=height,
                caption=(item.caption or item.original_name or "")[:255],
                status="pending",
                sort_order=next_order + index,
                uploaded_by_id=user.id,
            )
            db.add(photo)
            db.flush()
            item.applied_photo_id = photo.id
            photo_ids.append(photo.id)
        run.applied_activity_id = activity.id
        db.flush()
        run.applied_count = (
            db.query(PhotoSelectionItem)
            .filter(
                PhotoSelectionItem.run_id == run.id,
                PhotoSelectionItem.applied_photo_id.is_not(None),
            )
            .count()
        )
        learned = photo_curator.learn_from_run(db, run)
        audit(
            db,
            request,
            "PHOTO_SELECTION_APPLY",
            actor=user,
            entity_type="activity",
            entity_id=activity.id,
            summary=f"Menerapkan {len(photo_ids)} foto pilihan ke {activity.code}",
            detail={"run_id": run.id, "learned": bool(learned.get("updated"))},
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        for path in saved_paths:
            delete_paths(path)
        flash(request, f"Foto gagal diterapkan: {exc}", "danger")
        return RedirectResponse(f"/seleksi-foto/sesi/{run.id}", status_code=303)
    for photo_id in photo_ids:
        jobs.enqueue_photo(photo_id)
    flash(
        request,
        f"{len(photo_ids)} foto diterapkan ke kegiatan {activity.code} dan sedang diproses.",
        "success",
    )
    return RedirectResponse(f"/kegiatan/{activity.id}#galeri", status_code=303)


@router.get("/seleksi-foto/sesi/{run_id}/foto/{item_id}")
def download_selection_photo(
    run_id: int,
    item_id: int,
    user: User = Depends(ACCESS),
    db: Session = Depends(get_db),
):
    """Sajikan satu foto asli sebagai lampiran, bukan tautan atau arsip ZIP."""
    run = _own_run_or_404(db, run_id, user)
    item = db.get(PhotoSelectionItem, item_id)
    if item is None or item.run_id != run.id or not item.file_path:
        raise HTTPException(status_code=404, detail="Foto tidak ditemukan.")

    try:
        path = photo_curator.absolute_path(item.file_path)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Foto tidak ditemukan.") from exc

    if not path.is_file() and settings.media_cache_on_demand:
        from ..services import media_sync

        media_sync.download_to_cache(item.file_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Berkas foto tidak tersedia.")

    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    if media_type not in DOWNLOAD_IMAGE_TYPES:
        raise HTTPException(status_code=404, detail="Berkas bukan foto yang didukung.")

    return FileResponse(
        path,
        media_type=media_type,
        filename=_photo_download_name(item, path),
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.post("/seleksi-foto/sesi/{run_id}/hapus")
def delete_selection(
    run_id: int,
    request: Request,
    user: User = Depends(ACCESS),
    db: Session = Depends(get_db),
):
    run = _own_run_or_404(db, run_id, user)
    if run.status == SELECTION_RUNNING:
        flash(request, "Batalkan sesi terlebih dahulu sebelum menghapusnya.", "warning")
        return RedirectResponse(f"/seleksi-foto/sesi/{run.id}", status_code=303)
    paths: list[str] = []
    for item in run.items:
        paths.extend([item.file_path or "", item.thumb_path or ""])
    audit(
        db,
        request,
        "PHOTO_SELECTION_DELETE",
        actor=user,
        entity_type="photo_selection_run",
        entity_id=run.id,
        summary=f"Menghapus sesi seleksi foto #{run.id}",
    )
    db.delete(run)
    db.commit()
    for path in paths:
        delete_paths(path)
    flash(request, "Sesi seleksi dan berkas fotonya dihapus.", "success")
    return RedirectResponse("/seleksi-foto", status_code=303)
