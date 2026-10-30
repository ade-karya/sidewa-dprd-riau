"""Autentikasi, profil, dan token API."""

from __future__ import annotations

import re
import uuid
from datetime import timedelta
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from ..audit import audit
from ..config import settings
from ..constants import (
    CONTENT_MANAGER_ROLES,
    ROLE_ANGGOTA,
    ROLE_LABELS,
    ROLE_STAF_HUMAS,
)
from ..database import get_db
from ..deps import csrf_protect, flash, get_current_user, require_user
from ..models import (
    ApiToken,
    AuditLog,
    HumasStaff,
    HumasStaffAccount,
    HumasStaffFaceLogin,
    Member,
    MemberAccount,
    MemberFaceLogin,
    User,
    utcnow,
)
from ..security import (
    PasswordPolicyError,
    generate_api_token,
    generate_password,
    hash_password,
    new_csrf_token,
    validate_password_strength,
    verify_password,
)
from ..services import face_engine, photo_curator
from ..services.analytics import public_guide_stats
from ..services.images import (
    ImageValidationError,
    delete_paths,
    normalize_upload,
    save_image,
)
from ..templating import render

router = APIRouter(dependencies=[Depends(csrf_protect)])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _demo_accounts() -> list[dict]:
    if not settings.demo_mode:
        return []
    from ..services.seed import demo_credentials

    return demo_credentials()


def _safe_next(value: str | None) -> str:
    if not value:
        return "/"
    parsed = urlparse(value)
    if parsed.scheme or parsed.netloc or not value.startswith("/") or value.startswith("//"):
        return "/"
    if value.startswith("/login"):
        return "/"
    return value


def _face_members(db: Session) -> list[Member]:
    return (
        db.query(Member)
        .filter(Member.is_active.is_(True))
        .order_by(Member.commission_id.is_(None), Member.full_name)
        .all()
    )


def _face_registered_ids(db: Session) -> set[int]:
    return {
        row[0]
        for row in db.query(MemberFaceLogin.member_id)
        .filter(MemberFaceLogin.is_active.is_(True))
        .all()
    }


def _face_staff(db: Session) -> list[HumasStaff]:
    return (
        db.query(HumasStaff)
        .filter(HumasStaff.is_active.is_(True))
        .order_by(HumasStaff.sort_order, HumasStaff.full_name)
        .all()
    )


def _face_registered_staff_ids(db: Session) -> set[int]:
    return {
        row[0]
        for row in db.query(HumasStaffFaceLogin.staff_id)
        .filter(HumasStaffFaceLogin.is_active.is_(True))
        .all()
    }


def _detect_login_face(raw: bytes):
    """Validasi unggahan lalu deteksi satu wajah tanpa menyimpan berkas permanen."""
    normalized = normalize_upload(raw, max_dimension=1400)
    temp_dir = settings.media_root / "tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    path = temp_dir / f"face-login-{uuid.uuid4().hex}.jpg"
    path.write_bytes(normalized.data)
    try:
        return face_engine.engine.detect_single(path)
    finally:
        path.unlink(missing_ok=True)


def _member_user(db: Session, member: Member) -> tuple[User, MemberAccount]:
    account = db.query(MemberAccount).filter(MemberAccount.member_id == member.id).first()
    if account and account.user:
        return account.user, account
    username = f"anggota{member.id}"
    suffix = 1
    while db.query(User).filter(User.username == username).first():
        suffix += 1
        username = f"anggota{member.id}-{suffix}"
    user = User(
        username=username[:64],
        full_name=member.full_name[:160],
        email=member.email,
        role=ROLE_ANGGOTA,
        commission_id=member.commission_id,
        password_hash=hash_password(generate_password()),
        is_active=True,
        must_change_password=False,
    )
    db.add(user)
    db.flush()
    account = MemberAccount(user_id=user.id, member_id=member.id)
    db.add(account)
    db.flush()
    return user, account


def _staff_user(db: Session, staff: HumasStaff) -> tuple[User, HumasStaffAccount]:
    account = (
        db.query(HumasStaffAccount)
        .filter(HumasStaffAccount.staff_id == staff.id)
        .first()
    )
    if account and account.user:
        return account.user, account
    username = f"humas{staff.id}"
    suffix = 1
    while db.query(User).filter(User.username == username).first():
        suffix += 1
        username = f"humas{staff.id}-{suffix}"
    user = User(
        username=username[:64],
        full_name=staff.full_name[:160],
        email=staff.email,
        role=ROLE_STAF_HUMAS,
        password_hash=hash_password(generate_password()),
        is_active=True,
        must_change_password=False,
    )
    db.add(user)
    db.flush()
    account = HumasStaffAccount(user_id=user.id, staff_id=staff.id)
    db.add(account)
    db.flush()
    return user, account


def _start_session(request: Request, user: User, *, method: str = "password") -> None:
    request.session.clear()
    request.session["user_id"] = user.id
    request.session["csrf"] = new_csrf_token()
    request.session["auth_method"] = method


def _face_error(message: str, status_code: int = 400) -> JSONResponse:
    return JSONResponse({"ok": False, "error": message}, status_code=status_code)


@router.get("/login")
def login_page(request: Request, next: str = "", db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if user:
        return RedirectResponse("/", status_code=303)
    return render(
        request,
        "auth/login.html",
        user=None,
        next_path=_safe_next(next),
        demo_accounts=_demo_accounts(),
        face_members=_face_members(db),
        face_registered_ids=_face_registered_ids(db),
        face_staff=_face_staff(db),
        face_staff_registered_ids=_face_registered_staff_ids(db),
        face_available=face_engine.engine.available,
        stats=public_guide_stats(db),
    )


@router.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form("/"),
    db: Session = Depends(get_db),
):
    username = username.strip().lower()
    user = db.query(User).filter(User.username == username).first()
    error = None
    if user is None:
        # Tetap jalankan verifikasi dummy agar waktu respons seragam.
        verify_password(
            password,
            "$argon2id$v=19$m=65536,t=3,p=2$AAAAAAAAAAAAAAAAAAAAAA$AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
        )
        error = "Nama pengguna atau kata sandi salah."
    elif not user.is_active:
        error = "Akun dinonaktifkan. Hubungi administrator."
    elif user.locked_until and user.locked_until > utcnow():
        minutes = max(1, int((user.locked_until - utcnow()).total_seconds() // 60) + 1)
        error = f"Akun terkunci sementara. Coba lagi dalam {minutes} menit."
    elif not verify_password(password, user.password_hash):
        user.failed_attempts += 1
        if user.failed_attempts >= 5:
            user.locked_until = utcnow() + timedelta(minutes=15)
            user.failed_attempts = 0
        audit(
            db,
            request,
            "LOGIN_FAILED",
            entity_type="user",
            entity_id=user.id,
            summary=f"Gagal masuk untuk akun {user.username}",
            actor=user,
        )
        db.commit()
        error = "Nama pengguna atau kata sandi salah."

    if error:
        return render(
            request,
            "auth/login.html",
            user=None,
            status_code=401,
            error=error,
            username=username,
            next_path=_safe_next(next),
            demo_accounts=_demo_accounts(),
            face_members=_face_members(db),
            face_registered_ids=_face_registered_ids(db),
            face_staff=_face_staff(db),
            face_staff_registered_ids=_face_registered_staff_ids(db),
            face_available=face_engine.engine.available,
            stats=public_guide_stats(db),
        )

    user.failed_attempts = 0
    user.locked_until = None
    user.last_login_at = utcnow()
    audit(
        db,
        request,
        "LOGIN",
        entity_type="user",
        entity_id=user.id,
        summary=f"{user.full_name} masuk ke aplikasi",
        actor=user,
    )
    db.commit()

    _start_session(request, user, method="password")
    flash(request, f"Selamat datang, {user.full_name}.", "success")
    return RedirectResponse(_safe_next(next), status_code=303)


@router.post("/login/wajah")
async def login_with_face(
    request: Request,
    photo: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Masuk dengan Face ID yang sudah didaftarkan pada halaman login."""
    if not face_engine.engine.available:
        return _face_error(
            "Mesin pengenalan wajah tidak tersedia di server. Hubungi administrator.",
            503,
        )
    if not photo or not photo.filename:
        return _face_error("Ambil atau pilih foto wajah terlebih dahulu.")
    raw = await photo.read(settings.max_upload_bytes + 1)
    try:
        detected = _detect_login_face(raw)
    except ImageValidationError as exc:
        return _face_error(str(exc))
    except face_engine.FaceEngineError as exc:
        return _face_error(str(exc))

    known = face_engine.engine.known_login_faces(db)
    if not known:
        return _face_error(
            "Belum ada Face ID yang terdaftar. Daftarkan wajah terlebih dahulu.",
            404,
        )
    matches = face_engine.engine.match(detected.encoding, known)
    if not matches or matches[0].distance > settings.face_login_tolerance:
        audit(
            db,
            request,
            "FACE_LOGIN_FAILED",
            summary="Percobaan masuk dengan Face ID tidak dikenali",
            detail={"distance": matches[0].distance if matches else None},
        )
        db.commit()
        return _face_error(
            "Wajah tidak dikenali. Pastikan pencahayaan cukup dan wajah menghadap kamera.",
            401,
        )
    best = matches[0]
    if len(matches) > 1 and (matches[1].distance - best.distance) < settings.face_login_margin:
        audit(
            db,
            request,
            "FACE_LOGIN_FAILED",
            summary="Percobaan masuk Face ID ambigu (lebih dari satu kandidat)",
            detail={"distance": best.distance, "runner_up": matches[1].distance},
        )
        db.commit()
        return _face_error(
            "Wajah terlalu mirip dengan lebih dari satu orang. Gunakan foto yang lebih jelas.",
            401,
        )

    if best.kind == "staff":
        staff = db.get(HumasStaff, best.member_id)
        account = (
            db.query(HumasStaffAccount)
            .filter(HumasStaffAccount.staff_id == best.member_id)
            .first()
        )
        if not staff or not staff.is_active or not account or not account.user:
            return _face_error("Akun staf Humas tidak aktif. Hubungi Sekretariat DPRD.", 403)
        user = account.user
        if not user.is_active:
            return _face_error("Akun staf Humas dinonaktifkan. Hubungi administrator.", 403)
        login_face = db.get(HumasStaffFaceLogin, best.face_id)
        if login_face:
            login_face.last_used_at = utcnow()
        account.last_face_login_at = utcnow()
        user.failed_attempts = 0
        user.locked_until = None
        user.last_login_at = utcnow()
        audit(
            db,
            request,
            "FACE_LOGIN",
            actor=user,
            entity_type="staff",
            entity_id=staff.id,
            summary=f"{staff.full_name} masuk dengan Face ID sebagai staf Humas",
            detail={"confidence": best.confidence, "distance": best.distance},
        )
        db.commit()
        _start_session(request, user, method="face")
        flash(request, f"Selamat datang, {staff.full_name}.", "success")
        return JSONResponse(
            {
                "ok": True,
                "redirect": f"/dashboard-staf/{staff.id}",
                "name": staff.full_name,
                "confidence": best.confidence,
            }
        )

    member = db.get(Member, best.member_id)
    account = (
        db.query(MemberAccount).filter(MemberAccount.member_id == best.member_id).first()
    )
    if not member or not member.is_active or not account or not account.user:
        return _face_error("Akun anggota tidak aktif. Hubungi Sekretariat DPRD.", 403)
    user = account.user
    if not user.is_active:
        return _face_error("Akun anggota dinonaktifkan. Hubungi administrator.", 403)

    login_face = db.get(MemberFaceLogin, best.face_id)
    if login_face:
        login_face.last_used_at = utcnow()
    account.last_face_login_at = utcnow()
    user.failed_attempts = 0
    user.locked_until = None
    user.last_login_at = utcnow()
    audit(
        db,
        request,
        "FACE_LOGIN",
        actor=user,
        entity_type="member",
        entity_id=member.id,
        summary=f"{member.full_name} masuk dengan Face ID",
        detail={"confidence": best.confidence, "distance": best.distance},
    )
    db.commit()
    _start_session(request, user, method="face")
    flash(request, f"Selamat datang, {member.full_name}.", "success")
    return JSONResponse(
        {
            "ok": True,
            "redirect": f"/dashboard-anggota/{member.id}",
            "name": member.full_name,
            "confidence": best.confidence,
        }
    )


@router.post("/login/wajah/daftar")
async def enroll_face_login(
    request: Request,
    member_id: int | None = Form(None),
    staff_id: int | None = Form(None),
    subject: str = Form(""),
    photo: UploadFile = File(...),
    consent: bool = Form(False),
    db: Session = Depends(get_db),
):
    """Pendaftaran Face ID mandiri dari halaman login."""
    if not face_engine.engine.available:
        return _face_error(
            "Mesin pengenalan wajah tidak tersedia di server. Hubungi administrator.",
            503,
        )
    if not consent:
        return _face_error(
            "Centang persetujuan penggunaan data biometrik untuk melanjutkan."
        )

    kind = "member"
    subject_id = member_id
    if subject:
        raw_kind, _, raw_id = subject.partition(":")
        if raw_kind in {"member", "staff"} and raw_id.isdigit():
            kind = raw_kind
            subject_id = int(raw_id)
    elif staff_id:
        kind = "staff"
        subject_id = staff_id

    if not subject_id:
        return _face_error("Pilih nama Anda terlebih dahulu.")

    if kind == "staff":
        person = db.get(HumasStaff, subject_id)
        if not person or not person.is_active:
            return _face_error("Staf Humas tidak ditemukan atau sudah tidak aktif.", 404)
        existing = (
            db.query(HumasStaffFaceLogin)
            .filter(
                HumasStaffFaceLogin.staff_id == person.id,
                HumasStaffFaceLogin.is_active.is_(True),
            )
            .first()
        )
    else:
        person = db.get(Member, subject_id)
        if not person or not person.is_active:
            return _face_error("Anggota tidak ditemukan atau sudah tidak aktif.", 404)
        existing = (
            db.query(MemberFaceLogin)
            .filter(
                MemberFaceLogin.member_id == person.id,
                MemberFaceLogin.is_active.is_(True),
            )
            .first()
        )
    if existing:
        return _face_error(
            "Face ID untuk nama ini sudah terdaftar. Gunakan menu masuk dengan wajah.",
            409,
        )
    if not photo or not photo.filename:
        return _face_error("Ambil atau pilih foto wajah terlebih dahulu.")

    raw = await photo.read(settings.max_upload_bytes + 1)
    try:
        detected = _detect_login_face(raw)
    except ImageValidationError as exc:
        return _face_error(str(exc))
    except face_engine.FaceEngineError as exc:
        return _face_error(str(exc))

    known = face_engine.engine.known_login_faces(db)
    if known:
        matches = face_engine.engine.match(detected.encoding, known)
        if matches and matches[0].distance <= settings.face_login_tolerance:
            return _face_error(
                "Wajah ini sudah terdaftar untuk orang lain. Hubungi Sekretariat jika keliru.",
                409,
            )

    saved: list[str] = []
    try:
        rel_main, rel_thumb, _, _ = save_image(
            raw, "staff" if kind == "staff" else "members", max_dimension=1400
        )
        saved.extend([rel_main, rel_thumb])
        if kind == "staff":
            db.add(
                HumasStaffFaceLogin(
                    staff_id=person.id,
                    image_path=rel_main,
                    encoding=detected.encoding,
                    quality=detected.quality,
                )
            )
            user, account = _staff_user(db, person)
            if not user.is_active:
                raise ValueError("Akun staf Humas dinonaktifkan.")
            account.last_face_login_at = utcnow()
            if not person.consent_granted_at:
                person.consent_granted_at = utcnow()
                person.consent_note = "Persetujuan Face ID tercatat pada halaman login."
            entity_type = "staff"
            redirect = f"/dashboard-staf/{person.id}"
            message = f"Mendaftarkan Face ID untuk {person.full_name} (staf Humas) melalui halaman login"
        else:
            db.add(
                MemberFaceLogin(
                    member_id=person.id,
                    image_path=rel_main,
                    encoding=detected.encoding,
                    quality=detected.quality,
                )
            )
            user, account = _member_user(db, person)
            if not user.is_active:
                raise ValueError("Akun anggota dinonaktifkan.")
            account.last_face_login_at = utcnow()
            if not person.consent_granted_at:
                person.consent_granted_at = utcnow()
                person.consent_note = "Persetujuan Face ID tercatat pada halaman login."
            entity_type = "member"
            redirect = f"/dashboard-anggota/{person.id}"
            message = f"Mendaftarkan Face ID untuk {person.full_name} melalui halaman login"
        audit(
            db,
            request,
            "FACE_LOGIN_ENROLL",
            actor=user,
            entity_type=entity_type,
            entity_id=person.id,
            summary=message,
            detail={"quality": detected.quality},
        )
        db.commit()
    except Exception as exc:
        db.rollback()
        for path in saved:
            delete_paths(path)
        return _face_error(f"Pendaftaran Face ID gagal: {exc}", 400)

    _start_session(request, user, method="face")
    flash(request, f"Face ID {person.full_name} berhasil didaftarkan.", "success")
    return JSONResponse(
        {
            "ok": True,
            "redirect": redirect,
            "name": person.full_name,
        }
    )


@router.post("/logout")
def logout(
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    audit(
        db,
        request,
        "LOGOUT",
        actor=user,
        entity_type="user",
        entity_id=user.id,
        summary=f"{user.full_name} keluar dari aplikasi",
    )
    db.commit()
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


@router.get("/profil")
def profile(
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    tokens = (
        db.query(ApiToken)
        .filter(ApiToken.user_id == user.id)
        .order_by(ApiToken.created_at.desc())
        .all()
    )
    my_audit = (
        db.query(AuditLog)
        .filter(AuditLog.actor_id == user.id)
        .order_by(AuditLog.created_at.desc())
        .limit(10)
        .all()
    )
    ai_row = photo_curator.get_settings_row(db, user.id)
    ai_usage = None
    if ai_row:
        ai_usage = photo_curator.usage_snapshot(
            db, user.id, ai_row.rpm, ai_row.rpd, ai_row.tpm
        )
    return render(
        request,
        "auth/profile.html",
        user=user,
        tokens=tokens,
        my_audit=my_audit,
        ai_settings=ai_row,
        ai_usage=ai_usage,
        ai_available=user.role in CONTENT_MANAGER_ROLES,
        role_label=ROLE_LABELS.get(user.role, user.role),
    )


@router.post("/profil")
def update_profile(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(""),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    full_name = full_name.strip()
    email = email.strip().lower()
    if len(full_name) < 3:
        flash(request, "Nama lengkap minimal 3 karakter.", "danger")
        return RedirectResponse("/profil", status_code=303)
    if email and not _EMAIL_RE.match(email):
        flash(request, "Format email tidak valid.", "danger")
        return RedirectResponse("/profil", status_code=303)
    user.full_name = full_name
    user.email = email or None
    audit(
        db,
        request,
        "USER_UPDATE",
        actor=user,
        entity_type="user",
        entity_id=user.id,
        summary="Memperbarui profil sendiri",
    )
    db.commit()
    flash(request, "Profil berhasil diperbarui.", "success")
    return RedirectResponse("/profil", status_code=303)


@router.post("/profil/password")
def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    if not verify_password(current_password, user.password_hash):
        flash(request, "Kata sandi saat ini tidak sesuai.", "danger")
        return RedirectResponse("/profil", status_code=303)
    if new_password != confirm_password:
        flash(request, "Konfirmasi kata sandi baru tidak sama.", "danger")
        return RedirectResponse("/profil", status_code=303)
    try:
        validate_password_strength(new_password)
    except PasswordPolicyError as exc:
        flash(request, str(exc), "danger")
        return RedirectResponse("/profil", status_code=303)
    if verify_password(new_password, user.password_hash):
        flash(request, "Kata sandi baru harus berbeda dari kata sandi lama.", "danger")
        return RedirectResponse("/profil", status_code=303)
    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    audit(
        db,
        request,
        "USER_PASSWORD",
        actor=user,
        entity_type="user",
        entity_id=user.id,
        summary="Mengubah kata sandi sendiri",
    )
    db.commit()
    flash(request, "Kata sandi berhasil diubah.", "success")
    return RedirectResponse("/profil", status_code=303)


@router.post("/profil/token")
def create_token(
    request: Request,
    name: str = Form("Token integrasi"),
    days: int = Form(0),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    raw, prefix, token_hash = generate_api_token()
    expires = utcnow() + timedelta(days=days) if days > 0 else None
    token = ApiToken(
        user_id=user.id,
        name=name.strip()[:120] or "Token integrasi",
        prefix=prefix,
        token_hash=token_hash,
        expires_at=expires,
    )
    db.add(token)
    audit(
        db,
        request,
        "TOKEN_CREATE",
        actor=user,
        entity_type="api_token",
        summary=f"Membuat token API '{token.name}'",
    )
    db.commit()
    request.session["new_api_token"] = raw
    flash(
        request,
        "Token API berhasil dibuat. Salin sekarang — token tidak ditampilkan lagi.",
        "warning",
    )
    return RedirectResponse("/profil", status_code=303)


@router.post("/profil/token/{token_id}/hapus")
def revoke_token(
    token_id: int,
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    token = db.query(ApiToken).filter(ApiToken.id == token_id, ApiToken.user_id == user.id).first()
    if not token:
        flash(request, "Token tidak ditemukan.", "danger")
        return RedirectResponse("/profil", status_code=303)
    token.is_active = False
    audit(
        db,
        request,
        "TOKEN_REVOKE",
        actor=user,
        entity_type="api_token",
        entity_id=token.id,
        summary=f"Mencabut token API '{token.name}'",
    )
    db.commit()
    flash(request, "Token API dicabut.", "success")
    return RedirectResponse("/profil", status_code=303)
