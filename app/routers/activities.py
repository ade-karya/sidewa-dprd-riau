"""Pengelolaan dokumentasi kegiatan."""

from __future__ import annotations

import csv
import io
from datetime import date
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..audit import audit
from ..config import settings
from ..constants import (
    ADMIN_ROLES,
    CATEGORIES,
    CONTENT_MANAGER_ROLES,
    STATUS_ARCHIVED,
    STATUS_DRAFT,
    STATUS_PUBLISHED,
)
from ..database import get_db
from ..deps import csrf_protect, flash, require_roles, require_user
from ..models import (
    Activity,
    ActivityMember,
    ActivityPhoto,
    AuditLog,
    Commission,
    FaceDetection,
    Member,
    User,
    utcnow,
)
from ..services import jobs
from ..services.images import (
    ImageValidationError,
    delete_paths,
    save_image,
)
from ..services.search import Page, apply_filters, paginate, visible_query
from ..templating import render
from ..utils import local_now

router = APIRouter(dependencies=[Depends(csrf_protect)])

MANAGER = require_roles(*CONTENT_MANAGER_ROLES)
ADMIN = require_roles(*ADMIN_ROLES)


def _all_commissions(db: Session) -> list[Commission]:
    return (
        db.query(Commission)
        .filter(Commission.is_active.is_(True))
        .order_by(Commission.sort_order, Commission.code)
        .all()
    )


def _next_code(db: Session, year: int) -> str:
    prefix = f"KEG-{year}-"
    existing = {
        code for (code,) in db.query(Activity.code).filter(Activity.code.like(prefix + "%")).all()
    }
    counter = len(existing) + 1
    while f"{prefix}{counter:04d}" in existing:
        counter += 1
    return f"{prefix}{counter:04d}"


def _parse_date(value: str | None, field: str = "Tanggal") -> date:
    try:
        return date.fromisoformat((value or "").strip())
    except ValueError as exc:
        raise ValueError(f"{field} tidak valid.") from exc


def _parse_optional_float(value: str | None, field: str) -> float | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        number = float(value.replace(",", "."))
    except ValueError as exc:
        raise ValueError(f"{field} tidak valid.") from exc
    return number


def _commission_codes(form_codes: list[str], db: Session) -> list[str]:
    valid = {c.code for c in _all_commissions(db)}
    codes = [code for code in dict.fromkeys(form_codes) if code in valid]
    if not codes:
        raise ValueError("Pilih minimal satu komisi.")
    return codes


def _form_values(activity: Activity | None = None, *, db: Session, user: User) -> dict:
    if activity:
        return {
            "title": activity.title,
            "category": activity.category,
            "activity_date": activity.activity_date.isoformat(),
            "start_time": activity.start_time or "",
            "end_time": activity.end_time or "",
            "location_name": activity.location_name,
            "location_address": activity.location_address,
            "latitude": activity.latitude or "",
            "longitude": activity.longitude or "",
            "description": activity.description,
            "commission_codes": [c.code for c in activity.commissions],
        }
    commission_codes = []
    if user.commission:
        commission_codes = [user.commission.code]
    return {
        "title": "",
        "category": CATEGORIES[0],
        "activity_date": local_now().date().isoformat(),
        "start_time": "",
        "end_time": "",
        "location_name": "",
        "location_address": "",
        "latitude": "",
        "longitude": "",
        "description": "",
        "commission_codes": commission_codes,
    }


def _activity_or_404(db: Session, activity_id: int) -> Activity:
    activity = db.get(Activity, activity_id)
    if not activity:
        raise HTTPException(status_code=404, detail="Kegiatan tidak ditemukan.")
    return activity


def _check_visibility(activity: Activity, user: User) -> None:
    if activity.status != STATUS_PUBLISHED and user.role not in CONTENT_MANAGER_ROLES:
        raise HTTPException(status_code=404, detail="Kegiatan tidak ditemukan.")


def _order_by_newest(query):
    return query.order_by(Activity.activity_date.desc(), Activity.id.desc())


@router.get("/kegiatan")
def list_activities(
    request: Request,
    q: str = "",
    commission: str = "",
    category: str = "",
    location: str = "",
    date_from: str = "",
    date_to: str = "",
    status: str = "",
    page: int = 1,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    query = visible_query(db, user)
    date_from_value = None
    date_to_value = None
    try:
        if date_from:
            date_from_value = date.fromisoformat(date_from)
        if date_to:
            date_to_value = date.fromisoformat(date_to)
    except ValueError:
        flash(request, "Format tanggal filter tidak valid.", "warning")
    if status and user.role not in CONTENT_MANAGER_ROLES:
        status = ""
    query = apply_filters(
        query,
        q=q,
        commission=commission,
        category=category,
        location=location,
        date_from=date_from_value,
        date_to=date_to_value,
        status=status,
    )
    result: Page = paginate(_order_by_newest(query), page, 12)
    params = {
        key: value
        for key, value in {
            "q": q,
            "commission": commission,
            "category": category,
            "location": location,
            "date_from": date_from,
            "date_to": date_to,
            "status": status,
        }.items()
        if value
    }
    return render(
        request,
        "activities/list.html",
        user=user,
        result=result,
        commissions=_all_commissions(db),
        filters=params,
        q=q,
        commission=commission,
        category=category,
        location=location,
        date_from=date_from,
        date_to=date_to,
        status=status,
        query_string=urlencode(params),
    )


@router.get("/kegiatan/baru")
def new_activity(
    request: Request,
    user: User = Depends(MANAGER),
    db: Session = Depends(get_db),
):
    return render(
        request,
        "activities/form.html",
        user=user,
        activity=None,
        form=_form_values(db=db, user=user),
        commissions=_all_commissions(db),
        mode="create",
    )


@router.post("/kegiatan")
async def create_activity(
    request: Request,
    title: str = Form(...),
    category: str = Form(CATEGORIES[0]),
    activity_date: str = Form(...),
    start_time: str = Form(""),
    end_time: str = Form(""),
    location_name: str = Form(...),
    location_address: str = Form(""),
    latitude: str = Form(""),
    longitude: str = Form(""),
    description: str = Form(""),
    commissions: list[str] = Form([]),
    photos: list[UploadFile] = File(default=[]),
    user: User = Depends(MANAGER),
    db: Session = Depends(get_db),
):
    form = {
        "title": title,
        "category": category,
        "activity_date": activity_date,
        "start_time": start_time,
        "end_time": end_time,
        "location_name": location_name,
        "location_address": location_address,
        "latitude": latitude,
        "longitude": longitude,
        "description": description,
        "commission_codes": commissions,
    }
    saved_paths: list[str] = []
    try:
        title = title.strip()
        if len(title) < 5:
            raise ValueError("Judul kegiatan minimal 5 karakter.")
        if len(title) > 255:
            raise ValueError("Judul kegiatan maksimal 255 karakter.")
        if category not in CATEGORIES:
            category = "Lainnya"
        activity_date_value = _parse_date(activity_date)
        codes = _commission_codes(commissions, db)
        selected = [c for c in _all_commissions(db) if c.code in codes]
        lat = _parse_optional_float(latitude, "Latitude")
        lng = _parse_optional_float(longitude, "Longitude")
        if lat is not None and not -90 <= lat <= 90:
            raise ValueError("Latitude harus di antara -90 dan 90.")
        if lng is not None and not -180 <= lng <= 180:
            raise ValueError("Longitude harus di antara -180 dan 180.")
        files = [upload for upload in photos if upload and upload.filename]
        if len(files) > settings.max_photos_per_activity:
            raise ValueError(f"Maksimal {settings.max_photos_per_activity} foto per kegiatan.")
        if not location_name.strip():
            raise ValueError("Lokasi kegiatan wajib diisi.")

        activity = Activity(
            code=_next_code(db, activity_date_value.year),
            title=title,
            category=category,
            description=description.strip(),
            status=STATUS_DRAFT,
            activity_date=activity_date_value,
            start_time=start_time.strip() or None,
            end_time=end_time.strip() or None,
            location_name=location_name.strip()[:200],
            location_address=location_address.strip()[:400],
            latitude=lat,
            longitude=lng,
            commission_id=selected[0].id if len(selected) == 1 else None,
            created_by_id=user.id,
        )
        activity.commissions = selected
        db.add(activity)
        db.flush()

        for index, upload in enumerate(files, start=1):
            raw = await upload.read(settings.max_upload_bytes + 1)
            if len(raw) > settings.max_upload_bytes:
                raise ImageValidationError(
                    f"Foto {upload.filename} melebihi batas {settings.max_upload_mb} MB."
                )
            rel_main, rel_thumb, width, height = save_image(raw, "activities")
            saved_paths.extend([rel_main, rel_thumb])
            db.add(
                ActivityPhoto(
                    activity_id=activity.id,
                    file_path=rel_main,
                    thumb_path=rel_thumb,
                    width=width,
                    height=height,
                    caption="",
                    status="pending",
                    sort_order=index,
                    uploaded_by_id=user.id,
                )
            )
        audit(
            db,
            request,
            "ACTIVITY_CREATE",
            actor=user,
            entity_type="activity",
            entity_id=activity.id,
            summary=f"Membuat kegiatan {activity.code}: {activity.title}",
            detail={"photos": len(files)},
        )
        db.commit()
    except (ValueError, ImageValidationError) as exc:
        db.rollback()
        for path in saved_paths:
            delete_paths(path)
        return render(
            request,
            "activities/form.html",
            user=user,
            status_code=400,
            activity=None,
            form=form,
            commissions=_all_commissions(db),
            mode="create",
            error=str(exc),
        )
    except Exception:
        db.rollback()
        for path in saved_paths:
            delete_paths(path)
        raise

    photo_ids = [
        photo.id for photo in db.query(ActivityPhoto).filter_by(activity_id=activity.id).all()
    ]
    for photo_id in photo_ids:
        jobs.enqueue_photo(photo_id)
    flash(request, f"Kegiatan {activity.code} berhasil dibuat sebagai draf.", "success")
    if not photo_ids:
        flash(request, "Tambahkan foto dokumentasi agar wajah dapat dikenali otomatis.", "info")
    return RedirectResponse(f"/kegiatan/{activity.id}", status_code=303)


@router.get("/kegiatan/{activity_id}")
def activity_detail(
    activity_id: int,
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    activity = _activity_or_404(db, activity_id)
    _check_visibility(activity, user)
    activity.view_count += 1
    db.commit()
    photos = sorted(activity.photos, key=lambda p: (p.sort_order, p.id))
    detections_by_photo: dict[int, list[FaceDetection]] = {}
    for photo in photos:
        detections_by_photo[photo.id] = sorted(
            photo.detections, key=lambda d: (d.bbox_left, d.bbox_top)
        )
    members = db.query(Member).filter(Member.is_active.is_(True)).order_by(Member.full_name).all()
    related = (
        visible_query(db, user)
        .filter(Activity.id != activity.id)
        .filter(Activity.commissions.any(Commission.id.in_(activity.all_commission_ids)))
        .order_by(Activity.activity_date.desc())
        .limit(3)
        .all()
    )
    audit_entries = (
        db.query(AuditLog)
        .filter(AuditLog.entity_type == "activity", AuditLog.entity_id == activity.id)
        .order_by(AuditLog.created_at.desc())
        .limit(8)
        .all()
    )
    pending = any(photo.status in {"pending", "processing"} for photo in photos)
    return render(
        request,
        "activities/detail.html",
        user=user,
        activity=activity,
        photos=photos,
        detections_by_photo=detections_by_photo,
        members=members,
        related=related,
        audit_entries=audit_entries,
        pending=pending,
        failed_count=len([p for p in photos if p.status == "failed"]),
    )


@router.get("/kegiatan/{activity_id}/edit")
def edit_activity(
    activity_id: int,
    request: Request,
    user: User = Depends(MANAGER),
    db: Session = Depends(get_db),
):
    activity = _activity_or_404(db, activity_id)
    return render(
        request,
        "activities/form.html",
        user=user,
        activity=activity,
        form=_form_values(activity, db=db, user=user),
        commissions=_all_commissions(db),
        mode="edit",
    )


@router.post("/kegiatan/{activity_id}/edit")
async def update_activity(
    activity_id: int,
    request: Request,
    title: str = Form(...),
    category: str = Form(CATEGORIES[0]),
    activity_date: str = Form(...),
    start_time: str = Form(""),
    end_time: str = Form(""),
    location_name: str = Form(...),
    location_address: str = Form(""),
    latitude: str = Form(""),
    longitude: str = Form(""),
    description: str = Form(""),
    commissions: list[str] = Form([]),
    user: User = Depends(MANAGER),
    db: Session = Depends(get_db),
):
    activity = _activity_or_404(db, activity_id)
    form = {
        "title": title,
        "category": category,
        "activity_date": activity_date,
        "start_time": start_time,
        "end_time": end_time,
        "location_name": location_name,
        "location_address": location_address,
        "latitude": latitude,
        "longitude": longitude,
        "description": description,
        "commission_codes": commissions,
    }
    try:
        title = title.strip()
        if len(title) < 5:
            raise ValueError("Judul kegiatan minimal 5 karakter.")
        if category not in CATEGORIES:
            category = "Lainnya"
        activity_date_value = _parse_date(activity_date)
        codes = _commission_codes(commissions, db)
        selected = [c for c in _all_commissions(db) if c.code in codes]
        lat = _parse_optional_float(latitude, "Latitude")
        lng = _parse_optional_float(longitude, "Longitude")
        if lat is not None and not -90 <= lat <= 90:
            raise ValueError("Latitude harus di antara -90 dan 90.")
        if lng is not None and not -180 <= lng <= 180:
            raise ValueError("Longitude harus di antara -180 dan 180.")
        if not location_name.strip():
            raise ValueError("Lokasi kegiatan wajib diisi.")

        activity.title = title[:255]
        activity.category = category
        activity.description = description.strip()
        activity.activity_date = activity_date_value
        activity.start_time = start_time.strip() or None
        activity.end_time = end_time.strip() or None
        activity.location_name = location_name.strip()[:200]
        activity.location_address = location_address.strip()[:400]
        activity.latitude = lat
        activity.longitude = lng
        activity.commission_id = selected[0].id if len(selected) == 1 else None
        activity.commissions = selected
        audit(
            db,
            request,
            "ACTIVITY_UPDATE",
            actor=user,
            entity_type="activity",
            entity_id=activity.id,
            summary=f"Memperbarui kegiatan {activity.code}",
        )
        db.commit()
    except ValueError as exc:
        db.rollback()
        return render(
            request,
            "activities/form.html",
            user=user,
            status_code=400,
            activity=activity,
            form=form,
            commissions=_all_commissions(db),
            mode="edit",
            error=str(exc),
        )
    flash(request, "Kegiatan berhasil diperbarui.", "success")
    return RedirectResponse(f"/kegiatan/{activity.id}", status_code=303)


@router.post("/kegiatan/{activity_id}/terbit")
def publish_activity(
    activity_id: int,
    request: Request,
    user: User = Depends(MANAGER),
    db: Session = Depends(get_db),
):
    activity = _activity_or_404(db, activity_id)
    if not activity.photos:
        flash(request, "Tambahkan minimal satu foto sebelum menerbitkan kegiatan.", "danger")
        return RedirectResponse(f"/kegiatan/{activity.id}", status_code=303)
    activity.status = STATUS_PUBLISHED
    activity.published_at = utcnow()
    audit(
        db,
        request,
        "ACTIVITY_PUBLISH",
        actor=user,
        entity_type="activity",
        entity_id=activity.id,
        summary=f"Menerbitkan kegiatan {activity.code}",
    )
    db.commit()
    flash(request, "Kegiatan berhasil diterbitkan dan dapat diakses seluruh pengguna.", "success")
    return RedirectResponse(f"/kegiatan/{activity.id}", status_code=303)


@router.post("/kegiatan/{activity_id}/arsip")
def archive_activity(
    activity_id: int,
    request: Request,
    user: User = Depends(MANAGER),
    db: Session = Depends(get_db),
):
    activity = _activity_or_404(db, activity_id)
    activity.status = STATUS_ARCHIVED
    audit(
        db,
        request,
        "ACTIVITY_ARCHIVE",
        actor=user,
        entity_type="activity",
        entity_id=activity.id,
        summary=f"Mengarsipkan kegiatan {activity.code}",
    )
    db.commit()
    flash(request, "Kegiatan dipindahkan ke arsip.", "success")
    return RedirectResponse(f"/kegiatan/{activity.id}", status_code=303)


@router.post("/kegiatan/{activity_id}/pulihkan")
def restore_activity(
    activity_id: int,
    request: Request,
    user: User = Depends(MANAGER),
    db: Session = Depends(get_db),
):
    activity = _activity_or_404(db, activity_id)
    activity.status = STATUS_DRAFT
    activity.published_at = None
    audit(
        db,
        request,
        "ACTIVITY_UPDATE",
        actor=user,
        entity_type="activity",
        entity_id=activity.id,
        summary=f"Mengembalikan kegiatan {activity.code} ke draf",
    )
    db.commit()
    flash(request, "Kegiatan dikembalikan ke draf.", "success")
    return RedirectResponse(f"/kegiatan/{activity.id}", status_code=303)


@router.post("/kegiatan/{activity_id}/hapus")
def delete_activity(
    activity_id: int,
    request: Request,
    user: User = Depends(ADMIN),
    db: Session = Depends(get_db),
):
    activity = _activity_or_404(db, activity_id)
    for photo in activity.photos:
        delete_paths(photo.file_path, photo.thumb_path)
    audit(
        db,
        request,
        "ACTIVITY_DELETE",
        actor=user,
        entity_type="activity",
        entity_id=activity.id,
        summary=f"Menghapus kegiatan {activity.code}: {activity.title}",
    )
    db.delete(activity)
    db.commit()
    flash(request, "Kegiatan dan seluruh fotonya telah dihapus.", "success")
    return RedirectResponse("/kegiatan", status_code=303)


@router.post("/kegiatan/{activity_id}/foto")
async def add_photos(
    activity_id: int,
    request: Request,
    photos: list[UploadFile] = File(default=[]),
    user: User = Depends(MANAGER),
    db: Session = Depends(get_db),
):
    activity = _activity_or_404(db, activity_id)
    existing = db.query(ActivityPhoto).filter(ActivityPhoto.activity_id == activity.id).count()
    files = [upload for upload in photos if upload and upload.filename]
    if not files:
        flash(request, "Pilih minimal satu foto untuk diunggah.", "warning")
        return RedirectResponse(f"/kegiatan/{activity.id}", status_code=303)
    if existing + len(files) > settings.max_photos_per_activity:
        flash(
            request,
            f"Jumlah foto melebihi batas {settings.max_photos_per_activity} per kegiatan.",
            "danger",
        )
        return RedirectResponse(f"/kegiatan/{activity.id}", status_code=303)
    saved_paths: list[str] = []
    photo_ids: list[int] = []
    try:
        next_order = existing + 1
        for index, upload in enumerate(files):
            raw = await upload.read(settings.max_upload_bytes + 1)
            if len(raw) > settings.max_upload_bytes:
                raise ImageValidationError(
                    f"Foto {upload.filename} melebihi batas {settings.max_upload_mb} MB."
                )
            rel_main, rel_thumb, width, height = save_image(raw, "activities")
            saved_paths.extend([rel_main, rel_thumb])
            photo = ActivityPhoto(
                activity_id=activity.id,
                file_path=rel_main,
                thumb_path=rel_thumb,
                width=width,
                height=height,
                status="pending",
                sort_order=next_order + index,
                uploaded_by_id=user.id,
            )
            db.add(photo)
            db.flush()
            photo_ids.append(photo.id)
        audit(
            db,
            request,
            "PHOTO_UPLOAD",
            actor=user,
            entity_type="activity",
            entity_id=activity.id,
            summary=f"Menambahkan {len(files)} foto pada {activity.code}",
        )
        db.commit()
    except ImageValidationError as exc:
        db.rollback()
        for path in saved_paths:
            delete_paths(path)
        flash(request, str(exc), "danger")
        return RedirectResponse(f"/kegiatan/{activity.id}", status_code=303)
    for photo_id in photo_ids:
        jobs.enqueue_photo(photo_id)
    flash(request, f"{len(files)} foto berhasil diunggah dan sedang diproses.", "success")
    return RedirectResponse(f"/kegiatan/{activity.id}", status_code=303)


@router.post("/kegiatan/{activity_id}/foto/{photo_id}/hapus")
def delete_photo(
    activity_id: int,
    photo_id: int,
    request: Request,
    user: User = Depends(MANAGER),
    db: Session = Depends(get_db),
):
    activity = _activity_or_404(db, activity_id)
    photo = (
        db.query(ActivityPhoto)
        .filter(ActivityPhoto.id == photo_id, ActivityPhoto.activity_id == activity.id)
        .first()
    )
    if not photo:
        raise HTTPException(status_code=404, detail="Foto tidak ditemukan.")
    delete_paths(photo.file_path, photo.thumb_path)
    db.delete(photo)
    audit(
        db,
        request,
        "PHOTO_DELETE",
        actor=user,
        entity_type="activity",
        entity_id=activity.id,
        summary=f"Menghapus satu foto dari {activity.code}",
    )
    db.commit()
    flash(request, "Foto dihapus.", "success")
    return RedirectResponse(f"/kegiatan/{activity.id}", status_code=303)


@router.post("/kegiatan/{activity_id}/foto/{photo_id}/proses")
def reprocess_photo(
    activity_id: int,
    photo_id: int,
    request: Request,
    user: User = Depends(MANAGER),
    db: Session = Depends(get_db),
):
    activity = _activity_or_404(db, activity_id)
    photo = (
        db.query(ActivityPhoto)
        .filter(ActivityPhoto.id == photo_id, ActivityPhoto.activity_id == activity.id)
        .first()
    )
    if not photo:
        raise HTTPException(status_code=404, detail="Foto tidak ditemukan.")
    photo.status = "pending"
    photo.error = None
    db.commit()
    jobs.enqueue_photo(photo.id)
    flash(request, "Foto dimasukkan kembali ke antrean pemrosesan wajah.", "info")
    return RedirectResponse(f"/kegiatan/{activity.id}", status_code=303)


@router.post("/kegiatan/{activity_id}/anggota")
def add_member_tag(
    activity_id: int,
    request: Request,
    member_id: int = Form(...),
    user: User = Depends(MANAGER),
    db: Session = Depends(get_db),
):
    activity = _activity_or_404(db, activity_id)
    member = db.get(Member, member_id)
    if not member or not member.is_active:
        flash(request, "Anggota tidak ditemukan atau sudah tidak aktif.", "danger")
        return RedirectResponse(f"/kegiatan/{activity.id}", status_code=303)
    existing = (
        db.query(ActivityMember)
        .filter(
            ActivityMember.activity_id == activity.id,
            ActivityMember.member_id == member.id,
        )
        .first()
    )
    if existing:
        existing.confirmed = True
        flash(request, f"{member.full_name} sudah tertaut pada kegiatan ini.", "info")
    else:
        db.add(
            ActivityMember(
                activity_id=activity.id,
                member_id=member.id,
                source="manual",
                confirmed=True,
                added_by_id=user.id,
            )
        )
        audit(
            db,
            request,
            "MEMBER_ADD",
            actor=user,
            entity_type="activity",
            entity_id=activity.id,
            summary=f"Menambahkan {member.full_name} ke {activity.code}",
        )
        flash(request, f"{member.full_name} ditambahkan ke kegiatan.", "success")
    db.commit()
    return RedirectResponse(f"/kegiatan/{activity.id}#peserta", status_code=303)


@router.post("/kegiatan/{activity_id}/anggota/{member_id}/hapus")
def remove_member_tag(
    activity_id: int,
    member_id: int,
    request: Request,
    user: User = Depends(MANAGER),
    db: Session = Depends(get_db),
):
    activity = _activity_or_404(db, activity_id)
    link = (
        db.query(ActivityMember)
        .filter(
            ActivityMember.activity_id == activity.id,
            ActivityMember.member_id == member_id,
        )
        .first()
    )
    if not link:
        raise HTTPException(status_code=404, detail="Tautan anggota tidak ditemukan.")
    member_name = link.member.full_name if link.member else "Anggota"
    db.delete(link)
    audit(
        db,
        request,
        "MEMBER_REMOVE",
        actor=user,
        entity_type="activity",
        entity_id=activity.id,
        summary=f"Melepas {member_name} dari {activity.code}",
    )
    db.commit()
    flash(request, f"{member_name} dilepas dari kegiatan.", "success")
    return RedirectResponse(f"/kegiatan/{activity.id}#peserta", status_code=303)


@router.post("/deteksi/{detection_id}/konfirmasi")
def confirm_detection(
    detection_id: int,
    request: Request,
    member_id: int | None = Form(None),
    user: User = Depends(MANAGER),
    db: Session = Depends(get_db),
):
    detection = db.get(FaceDetection, detection_id)
    if not detection:
        raise HTTPException(status_code=404, detail="Deteksi wajah tidak ditemukan.")
    activity = detection.photo.activity
    target_id = member_id or detection.member_id
    member = db.get(Member, target_id) if target_id else None
    if not member or not member.is_active:
        flash(request, "Pilih anggota yang valid untuk dikonfirmasi.", "danger")
        return RedirectResponse(
            f"/kegiatan/{activity.id}#foto-{detection.photo_id}", status_code=303
        )
    detection.member_id = member.id
    detection.is_confirmed = True
    detection.is_rejected = False
    link = (
        db.query(ActivityMember)
        .filter(
            ActivityMember.activity_id == activity.id,
            ActivityMember.member_id == member.id,
        )
        .first()
    )
    if link:
        link.confirmed = True
    else:
        db.add(
            ActivityMember(
                activity_id=activity.id,
                member_id=member.id,
                source="confirmed",
                confirmed=True,
                added_by_id=user.id,
            )
        )
    audit(
        db,
        request,
        "FACE_CONFIRM",
        actor=user,
        entity_type="activity",
        entity_id=activity.id,
        summary=f"Mengonfirmasi {member.full_name} pada foto kegiatan {activity.code}",
    )
    db.commit()
    flash(request, f"Wajah dikonfirmasi sebagai {member.full_name}.", "success")
    return RedirectResponse(f"/kegiatan/{activity.id}#foto-{detection.photo_id}", status_code=303)


@router.post("/deteksi/{detection_id}/tolak")
def reject_detection(
    detection_id: int,
    request: Request,
    user: User = Depends(MANAGER),
    db: Session = Depends(get_db),
):
    detection = db.get(FaceDetection, detection_id)
    if not detection:
        raise HTTPException(status_code=404, detail="Deteksi wajah tidak ditemukan.")
    activity = detection.photo.activity
    detection.is_rejected = True
    detection.is_confirmed = False
    if detection.member_id:
        still_confirmed = (
            db.query(FaceDetection)
            .join(ActivityPhoto, FaceDetection.photo_id == ActivityPhoto.id)
            .filter(
                ActivityPhoto.activity_id == activity.id,
                FaceDetection.member_id == detection.member_id,
                FaceDetection.is_confirmed.is_(True),
                FaceDetection.id != detection.id,
            )
            .count()
        )
        if not still_confirmed:
            link = (
                db.query(ActivityMember)
                .filter(
                    ActivityMember.activity_id == activity.id,
                    ActivityMember.member_id == detection.member_id,
                    ActivityMember.source == "auto",
                )
                .first()
            )
            if link:
                db.delete(link)
    audit(
        db,
        request,
        "FACE_REJECT",
        actor=user,
        entity_type="activity",
        entity_id=activity.id,
        summary=f"Menolak satu deteksi wajah pada {activity.code}",
    )
    db.commit()
    flash(request, "Deteksi wajah ditolak.", "success")
    return RedirectResponse(f"/kegiatan/{activity.id}#foto-{detection.photo_id}", status_code=303)


@router.get("/kegiatan/{activity_id}/proses-status")
def processing_status(
    activity_id: int,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    activity = _activity_or_404(db, activity_id)
    _check_visibility(activity, user)
    counts = dict(
        db.query(ActivityPhoto.status, func.count(ActivityPhoto.id))
        .filter(ActivityPhoto.activity_id == activity.id)
        .group_by(ActivityPhoto.status)
        .all()
    )
    return {
        "pending": counts.get("pending", 0) + counts.get("processing", 0),
        "ready": counts.get("ready", 0),
        "failed": counts.get("failed", 0),
        "done": counts.get("pending", 0) + counts.get("processing", 0) == 0,
    }


@router.get("/ekspor/kegiatan.csv")
def export_csv(
    request: Request,
    q: str = "",
    commission: str = "",
    category: str = "",
    location: str = "",
    date_from: str = "",
    date_to: str = "",
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    query = visible_query(db, user)
    try:
        query = apply_filters(
            query,
            q=q,
            commission=commission,
            category=category,
            location=location,
            date_from=date.fromisoformat(date_from) if date_from else None,
            date_to=date.fromisoformat(date_to) if date_to else None,
        )
    except ValueError:
        pass
    rows = _order_by_newest(query).limit(5000).all()
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["Kode", "Judul", "Kategori", "Tanggal", "Komisi", "Lokasi", "Peserta", "Status"]
    )
    for activity in rows:
        writer.writerow(
            [
                activity.code,
                activity.title,
                activity.category,
                activity.activity_date.isoformat(),
                ", ".join(c.short_name for c in activity.commissions),
                activity.location_name,
                "; ".join(m.full_name for m in activity.members),
                activity.status,
            ]
        )
    content = "\ufeff" + buffer.getvalue()
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="dokumentasi-dprd-riau-{local_now():%Y%m%d}.csv"'
        },
    )
