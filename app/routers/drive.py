"""Drive bersama tim Humas: berkas di folder ``drive/`` HF S3 lewat rclone."""

from __future__ import annotations

import mimetypes
import os
import tempfile
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from ..audit import audit
from ..config import settings
from ..constants import CONTENT_MANAGER_ROLES
from ..database import get_db
from ..deps import csrf_protect, flash, require_roles
from ..models import User
from ..services import drive
from ..templating import render

router = APIRouter(prefix="/drive", dependencies=[Depends(csrf_protect)])

MEMBER = require_roles(*CONTENT_MANAGER_ROLES)


def _redirect(path: str | None = "") -> RedirectResponse:
    url = "/drive"
    if path:
        url += f"?path={quote(path, safe='/')}"
    return RedirectResponse(url, status_code=303)


def _context(path: str | None, q: str | None = "") -> dict:
    data = drive.listing(path)
    data.update(
        {
            "query": (q or "").strip(),
            "max_upload_mb": settings.drive_max_upload_mb,
            "drive_ready": drive.available(),
        }
    )
    if data["query"]:
        data["search"] = drive.search(data["query"])
    else:
        data["search"] = {"query": "", "results": [], "truncated": False}
    return data


def _empty_context(error: str) -> dict:
    return {
        "path": "",
        "entries": [],
        "crumbs": [{"label": "Drive", "path": ""}],
        "folder_count": 0,
        "file_count": 0,
        "total_size": 0,
        "query": "",
        "search": {"query": "", "results": [], "truncated": False},
        "max_upload_mb": settings.drive_max_upload_mb,
        "drive_ready": False,
        "error": error,
    }


@router.get("")
def index(
    request: Request,
    path: str = "",
    q: str = "",
    user: User = Depends(MEMBER),
):
    try:
        context = _context(path, q)
    except drive.DriveError as exc:
        context = _empty_context(str(exc))
    return render(request, "drive/index.html", user=user, **context)


@router.post("/unggah")
async def upload(
    request: Request,
    files: list[UploadFile] = File(default=[]),
    path: str = Form(""),
    user: User = Depends(MEMBER),
    db: Session = Depends(get_db),
):
    limit = settings.drive_max_upload_bytes
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
                        f"{upload.filename}: melebihi batas {settings.drive_max_upload_mb} MB."
                    )
                temporary.write(chunk)
            temporary.close()
            name = drive.upload_file(path, upload.filename, temporary_path)
            saved.append(name)
        except drive.DriveError as exc:
            errors.append(str(exc))
        finally:
            if not temporary.closed:
                temporary.close()
            temporary_path.unlink(missing_ok=True)
            await upload.close()

    if saved:
        audit(
            db,
            request,
            "DRIVE_UPLOAD",
            actor=user,
            entity_type="drive",
            summary=f"Unggah {len(saved)} berkas ke Drive: {', '.join(saved[:5])}",
            detail={"path": drive.normalize_dir(path), "files": saved[:20]},
        )
        flash(request, f"{len(saved)} berkas diunggah ke Drive.")
    for message in errors:
        flash(request, message, "error")
    return _redirect(path)


@router.post("/folder")
def create_folder(
    request: Request,
    path: str = Form(""),
    name: str = Form(""),
    user: User = Depends(MEMBER),
    db: Session = Depends(get_db),
):
    try:
        destination = drive.create_folder(path, name)
    except drive.DriveError as exc:
        flash(request, str(exc), "error")
        return _redirect(path)
    audit(
        db,
        request,
        "DRIVE_FOLDER",
        actor=user,
        entity_type="drive",
        summary=f"Buat folder Drive: {destination}",
        detail={"path": destination},
    )
    flash(request, "Folder dibuat.")
    return _redirect(path)


@router.post("/ubah-nama")
def rename(
    request: Request,
    path: str = Form(""),
    name: str = Form(""),
    kind: str = Form("file"),
    user: User = Depends(MEMBER),
    db: Session = Depends(get_db),
):
    try:
        destination = drive.rename_entry(path, name, kind == "folder")
    except drive.DriveError as exc:
        flash(request, str(exc), "error")
        return _redirect(path.rsplit("/", 1)[0] if "/" in path else "")
    audit(
        db,
        request,
        "DRIVE_RENAME",
        actor=user,
        entity_type="drive",
        summary=f"Ubah nama Drive: {path} → {destination.rsplit('/', 1)[-1]}",
        detail={"from": path, "to": destination},
    )
    flash(request, "Nama diperbarui.")
    parent = destination.rsplit("/", 1)[0] if "/" in destination else ""
    return _redirect(parent)


@router.post("/hapus")
def remove(
    request: Request,
    path: str = Form(""),
    kind: str = Form("file"),
    user: User = Depends(MEMBER),
    db: Session = Depends(get_db),
):
    parent = path.rsplit("/", 1)[0] if "/" in path else ""
    try:
        removed = drive.delete_entry(path, kind == "folder")
    except drive.DriveError as exc:
        flash(request, str(exc), "error")
        return _redirect(parent)
    audit(
        db,
        request,
        "DRIVE_DELETE",
        actor=user,
        entity_type="drive",
        summary=f"Hapus {'folder' if kind == 'folder' else 'berkas'} Drive: {removed}",
        detail={"path": removed, "kind": kind},
    )
    flash(request, "Berkas dihapus." if kind != "folder" else "Folder dihapus.")
    return _redirect(parent)


@router.get("/unduh")
def download(path: str = "", user: User = Depends(MEMBER)):
    try:
        temporary, name, mime = drive.download_file(path)
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
