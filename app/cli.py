"""Perintah baris perintah SIDEWA.

Contoh:
    python -m app.cli init-db
    python -m app.cli seed --force
    python -m app.cli create-user --username humas2 --name "Humas Baru" --role humas
    python -m app.cli reindex
    python -m app.cli stats
    python -m app.cli resync --truncate
    python -m app.cli hydrate --force
    python -m app.cli sync-status
"""

from __future__ import annotations

import argparse
import getpass
import json
import logging
import sys

logger = logging.getLogger("sidewa.cli")

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
    HumasStaff,
    HumasStaffFaceLogin,
    Member,
    utcnow,
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


def cmd_seed_staff(_args) -> int:
    """Isi tabel staf Humas dari daftar resmi (idempoten)."""
    init_db()
    from .services.seed import HUMAS_STAFF, _staff_portrait_source
    from .services.images import (
        ImageValidationError,
        copy_seed_image,
        delete_image,
        full_path,
    )

    db = _db()
    try:
        inserted = 0
        updated = 0
        replaced: list[str] = []
        for index, (full_name, position) in enumerate(HUMAS_STAFF, start=1):
            staff = db.query(HumasStaff).filter(HumasStaff.full_name == full_name).first()
            if staff:
                current = staff.portrait_path
                # Pasang foto baru atau naikkan thumbnail lama ke gambar utama.
                if not current or full_path(current) != current:
                    source = _staff_portrait_source(index, full_name)
                    if source:
                        try:
                            rel_main, _, _, _ = copy_seed_image(source, "staff")
                            if current:
                                replaced.append(current)
                            staff.portrait_path = rel_main
                            updated += 1
                        except (ImageValidationError, OSError):
                            logger.warning("Foto staf %s dilewati: %s", full_name, source)
                continue
            staff = HumasStaff(
                full_name=full_name,
                position=position,
                unit="Bagian Humas & Perpustakaan",
                sort_order=index,
                bio=(
                    f"{full_name} bertugas sebagai {position} di Bagian Humas & "
                    "Perpustakaan Sekretariat DPRD Provinsi Riau."
                ),
                is_active=True,
                consent_granted_at=utcnow(),
                consent_note="Data staf Humas Sekretariat DPRD Provinsi Riau.",
            )
            source = _staff_portrait_source(index, full_name)
            if source:
                try:
                    rel_main, _, _, _ = copy_seed_image(source, "staff")
                    staff.portrait_path = rel_main
                except (ImageValidationError, OSError):
                    logger.warning("Foto staf %s dilewati: %s", full_name, source)
            db.add(staff)
            inserted += 1
        db.commit()
        for old_path in replaced:
            delete_image(old_path)
        print(
            f"Staf Humas: {inserted} baru, "
            f"{len(HUMAS_STAFF) - inserted} sudah ada, "
            f"{updated} foto diperbarui."
        )
    finally:
        db.close()
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
    from .services import media_sync, supabase_sync

    supabase_sync._adopt_existing_schema()
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
        print(
            f"Staf Humas    : {db.query(HumasStaff).count()} "
            f"({db.query(HumasStaffFaceLogin).count()} Face ID)"
        )
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
        print(f"Sinkronisasi  : {supabase_sync.status()}")
        print(f"Media sync    : {media_sync.status()}")
        return 0
    finally:
        db.close()


def cmd_resync(args) -> int:
    init_db()
    from .services import media_sync, supabase_sync

    if not supabase_sync.enabled():
        print(
            "Supabase belum dikonfigurasi. Isi SIDEWA_SUPABASE_DATABASE_URL dan "
            "SIDEWA_SUPABASE_ADMIN_DATABASE_URL di .env.",
            file=sys.stderr,
        )
        return 1

    print("Menyiapkan skema Supabase…")
    try:
        supabase_sync.init_supabase_schema()
    except Exception as exc:
        print(f"Gagal menyiapkan skema Supabase: {exc}", file=sys.stderr)
        return 1

    print("Menyalin data lokal → Supabase…")
    try:
        counts = supabase_sync.copy_local_to_supabase(truncate=args.truncate)
    except Exception as exc:
        print(f"Resync gagal: {exc}", file=sys.stderr)
        return 1
    for name, count in counts.items():
        print(f"  {name:20s}: {count}")

    if settings.media_sync_enabled:
        if not settings.hf_s3_configured:
            print("HF S3 belum dikonfigurasi; media tidak diunggah.", file=sys.stderr)
        else:
            print("Mengunggah media ke HF S3…")
            try:
                total = media_sync.sync_all()
            except Exception as exc:
                print(f"Sinkronisasi media gagal: {exc}", file=sys.stderr)
                return 1
            print(f"  media terunggah     : {total}")

    print("Resync selesai.")
    return 0


def cmd_hydrate(args) -> int:
    init_db()
    from .services import supabase_sync

    if not supabase_sync.enabled():
        print("Supabase belum dikonfigurasi.", file=sys.stderr)
        return 1
    try:
        counts = supabase_sync.hydrate_from_supabase(force=args.force)
    except Exception as exc:
        print(f"Hydrate gagal: {exc}", file=sys.stderr)
        return 1
    if counts.get("skipped"):
        print("Database lokal tidak kosong. Gunakan --force untuk menimpa dari Supabase.")
        return 0
    print("Hydrate Supabase → lokal selesai:")
    for name, count in counts.items():
        print(f"  {name:20s}: {count}")
    return 0


def cmd_sync(args) -> int:
    init_db()
    from .services import supabase_sync

    if not supabase_sync.enabled():
        print("Supabase belum dikonfigurasi.", file=sys.stderr)
        return 1
    applied = supabase_sync.process_outbox(limit=args.limit or None)
    print(f"{applied} perubahan dikirim ke Supabase.")
    print(json.dumps(supabase_sync.status(), indent=2, default=str))
    return 0


def cmd_sync_status(_args) -> int:
    init_db()
    from .services import media_sync, supabase_sync

    supabase_sync._adopt_existing_schema()
    payload = {
        "database": supabase_sync.status(),
        "media": media_sync.status(),
    }
    print(json.dumps(payload, indent=2, default=str))
    return 0


def cmd_upgrade_portraits(args) -> int:
    """Naikkan potret lama (thumbnail) ke gambar utama resolusi penuh."""
    init_db()
    from .services import media_sync
    from .services.images import (
        ImageValidationError,
        copy_seed_image,
        ensure_thumbnail,
    )
    from .services.seed import ASSETS, HUMAS_STAFF, MEMBER_PORTRAITS, _staff_portrait_source

    dry_run = bool(getattr(args, "dry_run", False))
    db = _db()
    members_updated = staff_updated = skipped = 0
    try:
        for member in db.query(Member).all():
            current = member.portrait_path
            if current and not current.endswith("_thumb.jpg"):
                continue
            faces = sorted(
                member.faces,
                key=lambda face: (not face.is_primary, face.id or 0),
            )
            main = next(
                (
                    face.image_path
                    for face in faces
                    if face.image_path and not face.image_path.endswith("_thumb.jpg")
                ),
                None,
            )
            if main and not dry_run:
                # Pastikan thumbnail pendamping ada agar kartu/avatar tetap ringan.
                if ensure_thumbnail(main, thumb_dimension=760) is None:
                    main = None
            if not main:
                source_rel = MEMBER_PORTRAITS.get(member.full_name)
                source = ASSETS / source_rel if source_rel else None
                if not source or not source.exists():
                    skipped += 1
                    continue
                if not dry_run:
                    try:
                        main, _, _, _ = copy_seed_image(source, "members")
                    except (ImageValidationError, OSError):
                        logger.warning("Potret %s dilewati: %s", member.full_name, source)
                        skipped += 1
                        continue
            if not dry_run:
                member.portrait_path = main
            members_updated += 1

        for index, (full_name, _position) in enumerate(HUMAS_STAFF, start=1):
            staff = db.query(HumasStaff).filter(HumasStaff.full_name == full_name).first()
            if not staff or not staff.portrait_path:
                continue
            if not staff.portrait_path.endswith("_thumb.jpg"):
                continue
            source = _staff_portrait_source(index, full_name)
            if not source:
                skipped += 1
                continue
            if not dry_run:
                try:
                    main, _, _, _ = copy_seed_image(source, "staff")
                except (ImageValidationError, OSError):
                    logger.warning("Foto staf %s dilewati: %s", full_name, source)
                    skipped += 1
                    continue
                staff.portrait_path = main
            staff_updated += 1

        if not dry_run:
            db.commit()
            uploaded = media_sync.sync_all()
        else:
            uploaded = 0
        print(
            f"Potret: {staff_updated} staf, {members_updated} anggota "
            f"dinaikkan ke gambar utama, {skipped} dilewati"
            + (f", {uploaded} berkas diunggah" if uploaded else "")
            + (" (dry-run)." if dry_run else ".")
        )
    finally:
        db.close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="Utilitas SIDEWA")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init-db", help="Buat tabel database dan direktori media")
    p.set_defaults(func=cmd_init_db)

    p = sub.add_parser("seed", help="Isi database dengan data demo")
    p.add_argument("--force", action="store_true", help="Hapus data lama lalu buat ulang")
    p.set_defaults(func=cmd_seed)

    p = sub.add_parser("seed-staff", help="Isi tabel staf Humas dari daftar resmi (idempoten)")
    p.set_defaults(func=cmd_seed_staff)

    p = sub.add_parser(
        "upgrade-portraits",
        help="Naikkan potret staf/anggota lama dari thumbnail ke gambar utama",
    )
    p.add_argument("--dry-run", action="store_true", help="Hitung saja tanpa mengubah data")
    p.set_defaults(func=cmd_upgrade_portraits)

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

    p = sub.add_parser("resync", help="Salin seluruh data lokal ke Supabase")
    p.add_argument(
        "--truncate",
        action="store_true",
        help="Kosongkan tabel Supabase terlebih dahulu (hati-hati)",
    )
    p.set_defaults(func=cmd_resync)

    p = sub.add_parser("hydrate", help="Pulihkan cache lokal dari Supabase")
    p.add_argument("--force", action="store_true", help="Timpa data lokal yang ada")
    p.set_defaults(func=cmd_hydrate)

    p = sub.add_parser("sync", help="Kirim outbox lokal ke Supabase sekarang")
    p.add_argument("--limit", type=int, default=0, help="Batas jumlah baris (0 = default)")
    p.set_defaults(func=cmd_sync)

    p = sub.add_parser("sync-status", help="Tampilkan status sinkronisasi database & media")
    p.set_defaults(func=cmd_sync_status)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
