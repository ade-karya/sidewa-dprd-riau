"""Antrean pemrosesan wajah berbasis thread pool.

Untuk satu node ini cukup andal dan tidak membutuhkan Redis. Ketika skala
horizontal dibutuhkan, antarmuka `enqueue_photo` dapat dipindahkan ke
Celery/RQ tanpa mengubah pemanggil.
"""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor

from ..audit import audit
from ..config import settings
from ..database import SessionLocal
from ..models import ActivityMember, ActivityPhoto, FaceDetection, Member, utcnow
from . import face_engine
from .images import absolute_path

logger = logging.getLogger("sidewa.faces")

_executor: ThreadPoolExecutor | None = None
_executor_lock = threading.Lock()


def _get_executor() -> ThreadPoolExecutor:
    global _executor
    with _executor_lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(
                max_workers=max(1, settings.face_workers), thread_name_prefix="sidewa-face"
            )
        return _executor


def shutdown() -> None:
    global _executor
    with _executor_lock:
        if _executor is not None:
            _executor.shutdown(wait=False, cancel_futures=True)
            _executor = None


def enqueue_photo(photo_id: int) -> None:
    if settings.face_sync:
        process_photo(photo_id)
        return
    try:
        _get_executor().submit(process_photo, photo_id)
    except Exception:  # pragma: no cover - fallback ketika executor gagal
        logger.exception("Gagal menambahkan foto %s ke antrean; memproses sinkron.", photo_id)
        process_photo(photo_id)


def process_photo(photo_id: int) -> None:
    db = SessionLocal()
    try:
        photo = db.get(ActivityPhoto, photo_id)
        if photo is None:
            return
        if photo.status == "ready":
            return
        photo.status = "processing"
        photo.error = None
        db.commit()

        if not photo.file_path:
            raise face_engine.FaceEngineError("Berkas foto tidak tersedia.")

        path = absolute_path(photo.file_path)
        if not path.exists():
            raise face_engine.FaceEngineError("Berkas foto tidak ditemukan di penyimpanan.")

        faces, width, height = face_engine.engine.analyze(path)

        # Bersihkan hasil otomatis sebelumnya, pertahankan tag manual/konfirmasi.
        db.query(FaceDetection).filter(FaceDetection.photo_id == photo.id).delete(
            synchronize_session=False
        )
        auto_member_ids = [
            row.member_id
            for row in db.query(ActivityMember)
            .filter(
                ActivityMember.activity_id == photo.activity_id,
                ActivityMember.source == "auto",
            )
            .all()
        ]
        if auto_member_ids:
            db.query(ActivityMember).filter(
                ActivityMember.activity_id == photo.activity_id,
                ActivityMember.source == "auto",
            ).delete(synchronize_session=False)

        known = face_engine.engine.known_faces(db)
        activity = photo.activity
        confirmed_ids: set[int] = set()
        for detected in faces:
            matches = face_engine.engine.match(detected.encoding, known)
            best = matches[0] if matches else None
            if best is None and detected.quality < 0.08:
                # Abaikan false positive latar belakang / wajah terlalu kecil.
                continue
            confirmed = bool(best and best.distance <= settings.face_auto_tag)
            reviewed = bool(best and best.distance <= settings.face_review)
            member_id = best.member_id if reviewed else None
            detection = FaceDetection(
                photo_id=photo.id,
                member_id=member_id,
                bbox_top=detected.bbox[0],
                bbox_right=detected.bbox[1],
                bbox_bottom=detected.bbox[2],
                bbox_left=detected.bbox[3],
                encoding=detected.encoding,
                distance=best.distance if best else None,
                confidence=best.confidence if best else None,
                is_confirmed=confirmed,
                is_rejected=False,
            )
            db.add(detection)
            if confirmed and member_id is not None:
                confirmed_ids.add(member_id)

        for member_id in confirmed_ids:
            member = db.get(Member, member_id)
            if not member or not member.is_active:
                continue
            exists = (
                db.query(ActivityMember)
                .filter(
                    ActivityMember.activity_id == activity.id,
                    ActivityMember.member_id == member_id,
                )
                .first()
            )
            if not exists:
                db.add(
                    ActivityMember(
                        activity_id=activity.id,
                        member_id=member_id,
                        source="auto",
                        confirmed=True,
                    )
                )

        photo.status = "ready"
        photo.face_count = len(faces)
        photo.width = width or photo.width
        photo.height = height or photo.height
        photo.processed_at = utcnow()
        db.commit()
        _metrics_inc("photos_processed")
        logger.info(
            "Foto %s selesai diproses: %s wajah, %s anggota teridentifikasi.",
            photo.id,
            len(faces),
            len(confirmed_ids),
        )
    except Exception as exc:
        db.rollback()
        logger.exception("Pemrosesan wajah foto %s gagal", photo_id)
        try:
            photo = db.get(ActivityPhoto, photo_id)
            if photo is not None:
                photo.status = "failed"
                photo.error = str(exc)[:500]
                photo.processed_at = utcnow()
                audit(
                    db,
                    None,
                    "PHOTO_PROCESS_FAILED",
                    entity_type="activity_photo",
                    entity_id=photo.id,
                    summary=f"Pemrosesan wajah gagal: {str(exc)[:180]}",
                )
                db.commit()
        except Exception:
            db.rollback()
            logger.exception("Gagal menyimpan status gagal foto %s", photo_id)
        _metrics_inc("face_failures")
    finally:
        db.close()


def requeue_pending() -> int:
    """Antrekan ulang foto yang tertinggal saat aplikasi berhenti."""
    db = SessionLocal()
    try:
        # Dipanggil saat startup: seluruh worker sebelumnya sudah berhenti,
        # sehingga foto berstatus processing pasti tertinggal dan aman diulang.
        photos = (
            db.query(ActivityPhoto)
            .filter(ActivityPhoto.status.in_(["pending", "processing"]))
            .limit(200)
            .all()
        )
        for photo in photos:
            photo.status = "pending"
            photo.error = None
        db.commit()
        ids = [photo.id for photo in photos]
        count = len(ids)
    finally:
        db.close()
    for photo_id in ids:
        enqueue_photo(photo_id)
    return count


def _metrics_inc(name: str) -> None:
    try:
        from ..metrics import increment

        increment(name)
    except Exception:
        pass
