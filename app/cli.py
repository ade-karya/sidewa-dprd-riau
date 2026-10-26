"""Perintah baris perintah SIDEWA.

Contoh:
    python -m app.cli init-db
    python -m app.cli seed --force
    python -m app.cli create-user --username humas2 --name "Humas Baru" --role humas
    python -m app.cli reindex
    python -m app.cli stats
"""

from __future__ import annotations

import argparse
import getpass
import sys

from sqlalchemy import func

from .config import settings
from .constants import (
    ROLE_LABELS,
    ROLE_STAF,
    ROLES,
)
from .database import SessionLocal, init_db
from .models import (
    Activity,
    ActivityPhoto,
    AuditLog,
    Commission,
    Member,
    MemberFace,
    User,
)
from .security import PasswordPolicyError, hash_password, validate_password_strength


def _db():
    return SessionLocal()


def cmd_init_db(_args) -> int:
    init_db()
    print(f"Database siap: {settings.database_url}")
    print(f"Direktori media: {settings.media_root}")
    return 0


def cmd_seed(args) -> int:
    from .services.seed import seed_demo

    init_db()
    db = _db()
    try:
        result = seed_demo(db, force=args.force)
    finally:
        db.close()
    if result.get("skipped"):
        print(result["reason"])
        return 0
    print("Data demo berhasil dibuat:")
    for key, value in result.items():
        print(f"  {key:12s}: {value}")
    print("\nAkun demo:")
    from .services.seed import demo_credentials

    for account in demo_credentials():
        print(f"  {account['username']:12s} / {account['password']:18s}  {account['label']}")
    return 0


def cmd_create_user(args) -> int:
    init_db()
    db = _db()
    try:
        username = args.username.strip().lower()
        if db.query(User).filter(User.username == username).first():
            print(f"Username '{username}' sudah digunakan.", file=sys.stderr)
            return 1
        if args.role not in ROLES:
            print(f"Peran tidak valid. Pilihan: {', '.join(ROLES)}", file=sys.stderr)
            return 1
        password = args.password or getpass.getpass("Kata sandi: ")
        try:
            validate_password_strength(password)
        except PasswordPolicyError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        commission_id = None
        if args.commission:
            commission = db.query(Commission).filter(Commission.code == args.commission).first()
            if not commission:
                print(f"Komisi '{args.commission}' tidak ditemukan.", file=sys.stderr)
                return 1
            commission_id = commission.id
        if args.role == ROLE_STAF and not commission_id:
            print(
                "Peran Staf Komisi wajib menggunakan --commission (contoh: --commission I).",
                file=sys.stderr,
            )
            return 1
        user = User(
            username=username,
            full_name=args.name.strip() or username,
            email=(args.email or "").strip().lower() or None,
            role=args.role,
            commission_id=commission_id,
            password_hash=hash_password(password),
            is_active=True,
            must_change_password=not args.no_force_change,
        )
        db.add(user)
        db.add(
            AuditLog(
                actor_name="CLI",
                action="USER_CREATE",
                entity_type="user",
                summary=f"Membuat pengguna {username} melalui CLI",
            )
        )
        db.commit()
        print(f"Pengguna '{username}' dibuat dengan peran {ROLE_LABELS.get(args.role, args.role)}.")
        if user.must_change_password:
            print("Pengguna wajib mengganti kata sandi saat pertama masuk.")
        return 0
    finally:
        db.close()


def cmd_reindex(args) -> int:
    init_db()
    from .services import jobs

    db = _db()
    try:
        query = db.query(ActivityPhoto)
        if args.activity:
            query = query.filter(ActivityPhoto.activity_id == args.activity)
        photos = query.order_by(ActivityPhoto.id).all()
        for photo in photos:
            photo.status = "pending"
            photo.error = None
        db.commit()
        ids = [photo.id for photo in photos]
    finally:
        db.close()
    print(f"Memproses ulang {len(ids)} foto…")
    for index, photo_id in enumerate(ids, start=1):
        jobs.process_photo(photo_id)
        print(f"  [{index}/{len(ids)}] foto #{photo_id}", end="\r", flush=True)
    print(f"\nSelesai memproses {len(ids)} foto.")
    return 0


def cmd_stats(_args) -> int:
    init_db()
    db = _db()
    try:
        print(f"Aplikasi      : {settings.app_name} — {settings.organization}")
        print(f"Lingkungan    : {settings.app_env}")
        print(f"Database      : {settings.database_url.split('://', 1)[0]}")
        print(f"Media         : {settings.media_root}")
        print()
        print(f"Komisi        : {db.query(Commission).count()}")
        print(
            f"Anggota       : {db.query(Member).count()} ({db.query(Member).filter(Member.is_active.is_(True)).count()} aktif)"
        )
        print(f"Data wajah    : {db.query(MemberFace).count()}")
        print(f"Kegiatan      : {db.query(Activity).count()}")
        print(f"Foto          : {db.query(ActivityPhoto).count()}")
        status_rows = (
            db.query(ActivityPhoto.status, func.count(ActivityPhoto.id))
            .group_by(ActivityPhoto.status)
            .all()
        )
        for status, count in status_rows:
            print(f"  - {status:10s}: {count}")
        print(f"Pengguna      : {db.query(User).count()}")
        print(f"Log audit     : {db.query(AuditLog).count()}")
        return 0
    finally:
        db.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="Utilitas SIDEWA")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init-db", help="Buat tabel database dan direktori media")
    p.set_defaults(func=cmd_init_db)

    p = sub.add_parser("seed", help="Isi database dengan data demo")
    p.add_argument("--force", action="store_true", help="Hapus data lama lalu buat ulang")
    p.set_defaults(func=cmd_seed)

    p = sub.add_parser("create-user", help="Buat akun pengguna baru")
    p.add_argument("--username", required=True)
    p.add_argument("--name", default="")
    p.add_argument("--email", default="")
    p.add_argument("--role", default=ROLE_STAF, choices=ROLES)
    p.add_argument("--commission", default="", help="Kode komisi, contoh: I, II, V")
    p.add_argument("--password", default="", help="Kosongkan untuk diminta secara interaktif")
    p.add_argument(
        "--no-force-change", action="store_true", help="Jangan paksa ganti sandi saat login"
    )
    p.set_defaults(func=cmd_create_user)

    p = sub.add_parser("reindex", help="Proses ulang deteksi wajah seluruh foto")
    p.add_argument("--activity", type=int, default=0, help="Batasi pada ID kegiatan tertentu")
    p.set_defaults(func=cmd_reindex)

    p = sub.add_parser("stats", help="Tampilkan ringkasan data")
    p.set_defaults(func=cmd_stats)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
