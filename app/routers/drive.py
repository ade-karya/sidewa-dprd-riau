"""Drive Humas: ruang pribadi berkuota + area bersama tim di HF S3 lewat rclone."""

from __future__ import annotations

import logging
import mimetypes
import os
import tempfile
from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from ..audit import audit
from ..config import settings
from ..constants import ADMIN_ROLES, CONTENT_MANAGER_ROLES
from ..database import get_db
from ..deps import csrf_protect, flash, require_roles
from ..models import User
from ..services import drive
from ..templating import render
from ..utils import human_filesize

logger = logging.getLogger("sidewa.drive")

router = APIRouter(prefix="/drive", dependencies=[Depends(csrf_protect)])

MEMBER = require_roles(*CONTENT_MANAGER_ROLES)

SCOPES = {"pribadi", "tim"}


def _scope(value: str | None) -> str:
    return value if value in SCOPES else "pribadi"


def _is_admin(user: User) -> bool:
    return user.role in ADMIN_ROLES


def _resolve(
    db: Session, user: User, scope: str, owner: int | None
) -> tuple[str, User | None, str]:
    """Tentukan akar Drive yang boleh diakses beserta pemiliknya."""
    if scope == "tim":
        return drive.team_root(), None, "Drive tim"
    target = user
    if owner and owner != user.id:
        if not _is_admin(user):
            raise HTTPException(
                status_code=403, detail="Anda hanya dapat membuka Drive sendiri."
            )
        target = db.get(User, owner)
        if (
            not target
            or not target.is_active
            or target.role not in CONTENT_MANAGER_ROLES
        ):
            raise HTTPException(status_code=404, detail="Drive staf tidak ditemukan.")
    return drive.personal_root(target.id), target, "Drive saya"


def _redirect(
    scope: str = "pribadi", owner: int | None = None, path: str | None = ""
) -> RedirectResponse:
    base = "/drive/tim" if scope == "tim" else "/drive"
    params: dict[str, str] = {}
    if owner and scope != "tim":
        params["owner"] = str(owner)
    if path:
        params["path"] = path
    url = f"{base}?{urlencode(params)}" if params else base
    return RedirectResponse(url, status_code=303)


def _staff_options(db: Session, user: User) -> list[User]:
    if not _is_admin(user):
        return []
    return (
        db.query(User)
        .filter(User.role.in_(tuple(CONTENT_MANAGER_ROLES)), User.is_active.is_(True))
        .order_by(User.full_name)
        .all()
    )


def _context(
    db: Session,
    user: User,
    scope: str,
    owner: int | None,
    path: str | None,
    q: str | None,
) -> dict:
    root, target, label = _resolve(db, user, scope, owner)
    data = drive.listing(root, path, label)
    query = (q or "").strip()
    data.update(
        {
            "scope": scope,
            "owner": target.id if target and scope != "tim" else None,
            "target_user": target,
            "label": label,
            "query": query,
            "max_upload_mb": settings.drive_max_upload_mb,
            "drive_ready": drive.available(),
            "quota": drive.quota_state(root) if scope == "pribadi" else None,
            "staff_options": _staff_options(db, user),
            "search": (
                drive.search(root, query)
                if query
                else {"query": "", "results": [], "truncated": False}
            ),
        }
    )
    return data


def _empty_context(
    db: Session, user: User, scope: str, owner: int | None, error: str
) -> dict:
    return {
        "path": "",
        "entries": [],
        "crumbs": [{"label": "Drive", "path": ""}],
        "folder_count": 0,
        "file_count": 0,
        "total_size": 0,
        "scope": scope,
        "owner": owner,
        "target_user": None,
        "label": "Drive tim" if scope == "tim" else "Drive saya",
        "query": "",
        "search": {"query": "", "results": [], "truncated": False},
        "max_upload_mb": settings.drive_max_upload_mb,
        "drive_ready": False,
        "quota": None,
        "staff_options": _staff_options(db, user),
        "error": error,
    }


@router.get("")
def index(
    request: Request,
    path: str = "",
    q: str = "",
    scope: str = "pribadi",
    owner: int | None = None,
    user: User = Depends(MEMBER),
    db: Session = Depends(get_db),
):
    scope = _scope(scope)
    try:
        context = _context(db, user, scope, owner, path, q)
    except drive.DriveError as exc:
        context = _empty_context(db, user, scope, owner, str(exc))
    return render(request, "drive/index.html", user=user, **context)


@router.get("/tim")
def team_index(
    request: Request,
    path: str = "",
    q: str = "",
    user: User = Depends(MEMBER),
    db: Session = Depends(get_db),
):
    try:
        context = _context(db, user, "tim", None, path, q)
    except drive.DriveError as exc:
        context = _empty_context(db, user, "tim", None, str(exc))
    return render(request, "drive/index.html", user=user, **context)


@router.post("/unggah")
async def upload(
    request: Request,
    files: list[UploadFile] = File(default=[]),
    path: str = Form(""),
    scope: str = Form("pribadi"),
    owner: int | None = Form(None),
    user: User = Depends(MEMBER),
    db: Session = Depends(get_db),
):
    scope = _scope(scope)
    try:
        root, target, _ = _resolve(db, user, scope, owner)
    except HTTPException as exc:
        flash(request, str(exc.detail), "error")
        return _redirect(scope, owner)

    limit = settings.drive_max_upload_bytes
    quota_total = drive.quota_bytes()
    used = drive.usage(root) if scope == "pribadi" else 0
    saved: list[str] = []
    errors: list[str] = []

    for upload in files:
        if not upload.filename:
            continue
        temporary = tempfile.NamedTemporaryFile(
            prefix="sidewa-drive-", suffix=".part", delete=False
        )
        temporary_path = Path(temporary.name)
        try:
            size = 0
            while chunk := await upload.read(256 * 1024):
                size += len(chunk)
                if size > limit:
                    raise drive.DriveError(
                        f"{upload.filename}: melebihi batas {settings.drive_max_upload_mb} MB "
                        "per berkas."
                    )
                temporary.write(chunk)
            temporary.close()
            if scope == "pribadi" and used + size > quota_total:
                raise drive.DriveQuotaExceeded(
                    f"{upload.filename}: melebihi sisa kuota Drive "
                    f"({human_filesize(max(0, quota_total - used))} dari "
                    f"{human_filesize(quota_total)}). Hapus berkas lain lebih dulu."
                )
            name = drive.upload_file(root, path, upload.filename, temporary_path)
            saved.append(name)
            used += size
        except drive.DriveError as exc:
            errors.append(str(exc))
        finally:
            if not temporary.closed:
                temporary.close()
            temporary_path.unlink(missing_ok=True)
            await upload.close()

    if saved:
        drive.forget_usage(root)
        audit(
            db,
            request,
            "DRIVE_UPLOAD",
            actor=user,
            entity_type="drive",
            summary=(
                f"Unggah {len(saved)} berkas ke "
                f"{'Drive tim' if scope == 'tim' else 'Drive pribadi'}: "
                f"{', '.join(saved[:5])}"
            ),
            detail={
                "scope": scope,
                "owner": target.id if target else None,
                "path": drive.normalize_dir(path),
                "files": saved[:20],
            },
        )
        flash(request, f"{len(saved)} berkas diunggah.")
    for message in errors:
        flash(request, message, "error")
    return _redirect(scope, owner if scope == "pribadi" else None, path)


@router.post("/folder")
def create_folder(
    request: Request,
    path: str = Form(""),
    name: str = Form(""),
    scope: str = Form("pribadi"),
    owner: int | None = Form(None),
    user: User = Depends(MEMBER),
    db: Session = Depends(get_db),
):
    scope = _scope(scope)
    try:
        root, target, _ = _resolve(db, user, scope, owner)
        destination = drive.create_folder(root, path, name)
    except HTTPException as exc:
        flash(request, str(exc.detail), "error")
        return _redirect(scope, owner, path)
    except drive.DriveError as exc:
        flash(request, str(exc), "error")
        return _redirect(scope, owner, path)
    audit(
        db,
        request,
        "DRIVE_FOLDER",
        actor=user,
        entity_type="drive",
        summary=f"Buat folder {'Drive tim' if scope == 'tim' else 'Drive pribadi'}: {destination}",
        detail={
            "scope": scope,
            "owner": target.id if target else None,
            "path": destination,
        },
    )
    flash(request, "Folder dibuat.")
    return _redirect(scope, owner, path)


@router.post("/ubah-nama")
def rename(
    request: Request,
    path: str = Form(""),
    name: str = Form(""),
    kind: str = Form("file"),
    scope: str = Form("pribadi"),
    owner: int | None = Form(None),
    user: User = Depends(MEMBER),
    db: Session = Depends(get_db),
):
    scope = _scope(scope)
    parent = path.rsplit("/", 1)[0] if "/" in path else ""
    try:
        root, target, _ = _resolve(db, user, scope, owner)
        destination = drive.rename_entry(root, path, name, kind == "folder")
    except HTTPException as exc:
        flash(request, str(exc.detail), "error")
        return _redirect(scope, owner, parent)
    except drive.DriveError as exc:
        flash(request, str(exc), "error")
        return _redirect(scope, owner, parent)
    audit(
        db,
        request,
        "DRIVE_RENAME",
        actor=user,
        entity_type="drive",
        summary=f"Ubah nama berkas Drive: {path} → {destination.rsplit('/', 1)[-1]}",
        detail={
            "scope": scope,
            "owner": target.id if target else None,
            "from": path,
            "to": destination,
        },
    )
    flash(request, "Nama diperbarui.")
    new_parent = destination.rsplit("/", 1)[0] if "/" in destination else ""
    return _redirect(scope, owner, new_parent)


@router.post("/hapus")
def remove(
    request: Request,
    path: str = Form(""),
    kind: str = Form("file"),
    scope: str = Form("pribadi"),
    owner: int | None = Form(None),
    user: User = Depends(MEMBER),
    db: Session = Depends(get_db),
):
    scope = _scope(scope)
    parent = path.rsplit("/", 1)[0] if "/" in path else ""
    try:
        root, target, _ = _resolve(db, user, scope, owner)
        removed = drive.delete_entry(root, path, kind == "folder")
    except HTTPException as exc:
        flash(request, str(exc.detail), "error")
        return _redirect(scope, owner, parent)
    except drive.DriveError as exc:
        flash(request, str(exc), "error")
        return _redirect(scope, owner, parent)
    audit(
        db,
        request,
        "DRIVE_DELETE",
        actor=user,
        entity_type="drive",
        summary=f"Hapus {'folder' if kind == 'folder' else 'berkas'} Drive: {removed}",
        detail={
            "scope": scope,
            "owner": target.id if target else None,
            "path": removed,
            "kind": kind,
        },
    )
    flash(request, "Berkas dihapus." if kind != "folder" else "Folder dihapus.")
    return _redirect(scope, owner, parent)


@router.get("/unduh")
def download(
    path: str = "",
    scope: str = "pribadi",
    owner: int | None = None,
    direct: bool = True,
    user: User = Depends(MEMBER),
    db: Session = Depends(get_db),
):
    scope = _scope(scope)
    try:
        root, _, _ = _resolve(db, user, scope, owner)
    except HTTPException:
        raise
    except drive.DriveError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    # Unduhan normal: alihkan browser ke presigned URL HF S3 (langsung ke CDN),
    # sehingga byte berkas tidak melewati server aplikasi. Berkas HTML/SVG/teks
    # tetap dialirkan lewat server agar tidak dirender inline oleh browser.
    file_name = path.rsplit("/", 1)[-1]
    if direct and not drive.should_stream(file_name):
        try:
            url = drive.presigned_url(root, path)
        except drive.DriveError as exc:
            logger.warning("Drive: tautan langsung gagal, memakai streaming (%s)", exc)
        else:
            return RedirectResponse(
                url,
                status_code=302,
                headers={"Cache-Control": "no-store"},
            )

    try:
        temporary, name, mime = drive.download_file(root, path)
    except drive.DriveError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(
        temporary,
        media_type=mime or mimetypes.guess_type(name)[0] or "application/octet-stream",
        filename=name,
        background=BackgroundTask(_cleanup, temporary),
    )


def _cleanup(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass
