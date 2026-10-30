"""Pengelolaan rilis (siaran pers) Humas Sekretariat DPRD."""

from __future__ import annotations

from datetime import date
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from ..audit import audit
from ..constants import (
    ADMIN_ROLES,
    CONTENT_MANAGER_ROLES,
    STATUS_ARCHIVED,
    STATUS_DRAFT,
    STATUS_PUBLISHED,
    STATUSES,
)
from ..database import get_db
from ..deps import csrf_protect, flash, require_roles, require_user
from ..models import Activity, PressRelease, User, utcnow
from ..services.releases import (
    apply_filters,
    next_code,
    status_counts,
    unique_slug,
    visible_query,
)
from ..services.search import Page, paginate
from ..templating import render
from ..utils import local_now

router = APIRouter(dependencies=[Depends(csrf_protect)])

MANAGER = require_roles(*CONTENT_MANAGER_ROLES)
ADMIN = require_roles(*ADMIN_ROLES)


def _release_or_404(db: Session, release_id: int) -> PressRelease:
    release = db.get(PressRelease, release_id)
    if not release:
        raise HTTPException(status_code=404, detail="Rilis tidak ditemukan.")
    return release


def _check_visibility(release: PressRelease, user: User) -> None:
    if release.status != STATUS_PUBLISHED and user.role not in CONTENT_MANAGER_ROLES:
        raise HTTPException(status_code=404, detail="Rilis tidak ditemukan.")


def _activity_options(db: Session) -> list[Activity]:
    return (
        db.query(Activity)
        .order_by(Activity.activity_date.desc(), Activity.id.desc())
        .limit(200)
        .all()
    )


def _form_values(release: PressRelease | None = None) -> dict:
    if release:
        return {
            "title": release.title,
            "summary": release.summary,
            "body": release.body,
            "release_date": release.release_date.isoformat(),
            "activity_id": str(release.activity_id or ""),
            "tags": ", ".join(release.tag_list),
        }
    return {
        "title": "",
        "summary": "",
        "body": "",
        "release_date": local_now().date().isoformat(),
        "activity_id": "",
        "tags": "",
    }


def _parse_date(value: str | None, field: str = "Tanggal rilis") -> date:
    try:
        return date.fromisoformat((value or "").strip())
    except ValueError as exc:
        raise ValueError(f"{field} tidak valid.") from exc


def _parse_tags(value: str | None) -> list[str]:
    raw = (value or "").replace(";", ",").replace("\n", ",")
    tags: list[str] = []
    seen: set[str] = set()
    for item in raw.split(","):
        tag = " ".join(item.split())[:40]
        key = tag.lower()
        if tag and key not in seen and len(tags) < 12:
            seen.add(key)
            tags.append(tag)
    return tags


def _parse_activity(db: Session, value: str | None) -> Activity | None:
    text = (value or "").strip()
    if not text:
        return None
    try:
        activity_id = int(text)
    except ValueError as exc:
        raise ValueError("Kegiatan terkait tidak valid.") from exc
    activity = db.get(Activity, activity_id)
    if not activity:
        raise ValueError("Kegiatan terkait tidak ditemukan.")
    return activity


def _validate_form(
    db: Session,
    *,
    title: str,
    summary: str,
    body: str,
    release_date: str,
    activity_id: str,
    tags: str,
) -> dict:
    title = " ".join(title.split())
    summary = " ".join(summary.split())
    body = body.strip()
    tags_value = _parse_tags(tags)
    if len(title) < 8:
        raise ValueError("Judul rilis minimal 8 karakter.")
    if len(title) > 255:
        raise ValueError("Judul rilis maksimal 255 karakter.")
    if len(summary) > 500:
        raise ValueError("Ringkasan rilis maksimal 500 karakter.")
    if len(body) < 40:
        raise ValueError("Isi rilis minimal 40 karakter.")
    release_date_value = _parse_date(release_date)
    activity = _parse_activity(db, activity_id)
    return {
        "title": title,
        "summary": summary,
        "body": body,
        "release_date": release_date_value,
        "activity": activity,
        "tags": tags_value,
    }


@router.get("/rilis")
def list_releases(
    request: Request,
    q: str = "",
    status: str = "",
    date_from: str = "",
    date_to: str = "",
    saya: str = "",
    page: int = 1,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    base = visible_query(db, user)
    if saya == "1":
        base = base.filter(PressRelease.author_id == user.id)

    counts = status_counts(base)

    query = base
    date_from_value = None
    date_to_value = None
    try:
        if date_from:
            date_from_value = date.fromisoformat(date_from)
        if date_to:
            date_to_value = date.fromisoformat(date_to)
    except ValueError:
        flash(request, "Format tanggal filter tidak valid.", "warning")

    if status and (status not in STATUSES or user.role not in CONTENT_MANAGER_ROLES):
        status = ""
    query = apply_filters(
        query,
        q=q,
        status=status or None,
        date_from=date_from_value,
        date_to=date_to_value,
    )
    result: Page = paginate(
        query.order_by(PressRelease.release_date.desc(), PressRelease.id.desc()),
        page,
        9,
    )
    params = {
        key: value
        for key, value in {
            "q": q,
            "status": status,
            "date_from": date_from,
            "date_to": date_to,
            "saya": saya,
        }.items()
        if value
    }
    return render(
        request,
        "releases/list.html",
        user=user,
        result=result,
        counts=counts,
        q=q,
        status=status,
        date_from=date_from,
        date_to=date_to,
        saya=saya,
        query_string=urlencode(params),
    )


@router.get("/rilis/baru")
def new_release(
    request: Request,
    user: User = Depends(MANAGER),
    db: Session = Depends(get_db),
):
    return render(
        request,
        "releases/form.html",
        user=user,
        release=None,
        form=_form_values(),
        activities=_activity_options(db),
        mode="create",
    )


@router.post("/rilis")
def create_release(
    request: Request,
    title: str = Form(...),
    summary: str = Form(""),
    body: str = Form(""),
    release_date: str = Form(""),
    activity_id: str = Form(""),
    tags: str = Form(""),
    user: User = Depends(MANAGER),
    db: Session = Depends(get_db),
):
    form = {
        "title": title,
        "summary": summary,
        "body": body,
        "release_date": release_date,
        "activity_id": activity_id,
        "tags": tags,
    }
    try:
        values = _validate_form(
            db,
            title=title,
            summary=summary,
            body=body,
            release_date=release_date,
            activity_id=activity_id,
            tags=tags,
        )
        release = PressRelease(
            code=next_code(db, values["release_date"].year),
            title=values["title"],
            slug=unique_slug(db, values["title"]),
            summary=values["summary"],
            body=values["body"],
            status=STATUS_DRAFT,
            release_date=values["release_date"],
            activity_id=values["activity"].id if values["activity"] else None,
            author_id=user.id,
            tags=values["tags"] or None,
        )
        db.add(release)
        db.flush()
        audit(
            db,
            request,
            "RELEASE_CREATE",
            actor=user,
            entity_type="release",
            entity_id=release.id,
            summary=f"Membuat draf rilis {release.code}: {release.title}",
        )
        db.commit()
    except ValueError as exc:
        db.rollback()
        return render(
            request,
            "releases/form.html",
            user=user,
            status_code=400,
            release=None,
            form=form,
            activities=_activity_options(db),
            mode="create",
            error=str(exc),
        )
    flash(request, f"Draf rilis {release.code} berhasil dibuat.", "success")
    return RedirectResponse(f"/rilis/{release.id}", status_code=303)


@router.get("/rilis/{release_id}")
def release_detail(
    release_id: int,
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    release = _release_or_404(db, release_id)
    _check_visibility(release, user)
    if release.status == STATUS_PUBLISHED:
        release.view_count += 1
        db.commit()
    related_query = db.query(PressRelease).filter(
        PressRelease.id != release.id,
        PressRelease.status == STATUS_PUBLISHED,
    )
    if release.activity_id:
        related_query = related_query.filter(
            PressRelease.activity_id == release.activity_id
        )
    else:
        related_query = related_query.filter(
            PressRelease.author_id == release.author_id
        )
    related = related_query.order_by(
        PressRelease.release_date.desc(), PressRelease.id.desc()
    ).limit(3).all()
    return render(
        request,
        "releases/detail.html",
        user=user,
        release=release,
        related=related,
    )


@router.get("/rilis/{release_id}/edit")
def edit_release(
    release_id: int,
    request: Request,
    user: User = Depends(MANAGER),
    db: Session = Depends(get_db),
):
    release = _release_or_404(db, release_id)
    return render(
        request,
        "releases/form.html",
        user=user,
        release=release,
        form=_form_values(release),
        activities=_activity_options(db),
        mode="edit",
    )


@router.post("/rilis/{release_id}/edit")
def update_release(
    release_id: int,
    request: Request,
    title: str = Form(...),
    summary: str = Form(""),
    body: str = Form(""),
    release_date: str = Form(""),
    activity_id: str = Form(""),
    tags: str = Form(""),
    user: User = Depends(MANAGER),
    db: Session = Depends(get_db),
):
    release = _release_or_404(db, release_id)
    form = {
        "title": title,
        "summary": summary,
        "body": body,
        "release_date": release_date,
        "activity_id": activity_id,
        "tags": tags,
    }
    try:
        values = _validate_form(
            db,
            title=title,
            summary=summary,
            body=body,
            release_date=release_date,
            activity_id=activity_id,
            tags=tags,
        )
        release.title = values["title"]
        release.summary = values["summary"]
        release.body = values["body"]
        release.release_date = values["release_date"]
        release.activity_id = values["activity"].id if values["activity"] else None
        release.tags = values["tags"] or None
        audit(
            db,
            request,
            "RELEASE_UPDATE",
            actor=user,
            entity_type="release",
            entity_id=release.id,
            summary=f"Memperbarui rilis {release.code}",
        )
        db.commit()
    except ValueError as exc:
        db.rollback()
        return render(
            request,
            "releases/form.html",
            user=user,
            status_code=400,
            release=release,
            form=form,
            activities=_activity_options(db),
            mode="edit",
            error=str(exc),
        )
    flash(request, "Rilis berhasil diperbarui.", "success")
    return RedirectResponse(f"/rilis/{release.id}", status_code=303)


@router.post("/rilis/{release_id}/terbit")
def publish_release(
    release_id: int,
    request: Request,
    user: User = Depends(MANAGER),
    db: Session = Depends(get_db),
):
    release = _release_or_404(db, release_id)
    if len((release.body or "").strip()) < 40:
        flash(request, "Lengkapi isi rilis sebelum menerbitkan.", "danger")
        return RedirectResponse(f"/rilis/{release.id}/edit", status_code=303)
    release.status = STATUS_PUBLISHED
    release.published_at = utcnow()
    audit(
        db,
        request,
        "RELEASE_PUBLISH",
        actor=user,
        entity_type="release",
        entity_id=release.id,
        summary=f"Menerbitkan rilis {release.code}",
    )
    db.commit()
    flash(request, "Rilis diterbitkan dan dapat dibaca seluruh pengguna.", "success")
    return RedirectResponse(f"/rilis/{release.id}", status_code=303)


@router.post("/rilis/{release_id}/arsip")
def archive_release(
    release_id: int,
    request: Request,
    user: User = Depends(MANAGER),
    db: Session = Depends(get_db),
):
    release = _release_or_404(db, release_id)
    release.status = STATUS_ARCHIVED
    audit(
        db,
        request,
        "RELEASE_ARCHIVE",
        actor=user,
        entity_type="release",
        entity_id=release.id,
        summary=f"Mengarsipkan rilis {release.code}",
    )
    db.commit()
    flash(request, "Rilis dipindahkan ke arsip.", "success")
    return RedirectResponse(f"/rilis/{release.id}", status_code=303)


@router.post("/rilis/{release_id}/pulihkan")
def restore_release(
    release_id: int,
    request: Request,
    user: User = Depends(MANAGER),
    db: Session = Depends(get_db),
):
    release = _release_or_404(db, release_id)
    release.status = STATUS_DRAFT
    release.published_at = None
    audit(
        db,
        request,
        "RELEASE_UPDATE",
        actor=user,
        entity_type="release",
        entity_id=release.id,
        summary=f"Mengembalikan rilis {release.code} ke draf",
    )
    db.commit()
    flash(request, "Rilis dikembalikan ke draf.", "success")
    return RedirectResponse(f"/rilis/{release.id}", status_code=303)


@router.post("/rilis/{release_id}/hapus")
def delete_release(
    release_id: int,
    request: Request,
    user: User = Depends(ADMIN),
    db: Session = Depends(get_db),
):
    release = _release_or_404(db, release_id)
    audit(
        db,
        request,
        "RELEASE_DELETE",
        actor=user,
        entity_type="release",
        entity_id=release.id,
        summary=f"Menghapus rilis {release.code}: {release.title}",
    )
    db.delete(release)
    db.commit()
    flash(request, "Rilis telah dihapus.", "success")
    return RedirectResponse("/rilis", status_code=303)
