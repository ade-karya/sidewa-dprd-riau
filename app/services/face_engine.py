"""Mesin pengenalan wajah di atas library face_recognition + dlib."""

from __future__ import annotations

import sys
import threading
import warnings
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image
from sqlalchemy.orm import Session

from ..config import settings

# Dukungan ketika aplikasi dijalankan langsung dari repository face_recognition.
_REPO_ROOT = Path(__file__).resolve().parents[3]
if (_REPO_ROOT / "face_recognition" / "__init__.py").exists():
    sys.path.insert(0, str(_REPO_ROOT))

warnings.filterwarnings("ignore", message="pkg_resources is deprecated.*")

try:  # pragma: no cover - bergantung pada instalasi dlib
    import face_recognition  # type: ignore

    _IMPORT_ERROR: str | None = None
except Exception as exc:  # pragma: no cover
    face_recognition = None  # type: ignore
    _IMPORT_ERROR = str(exc)


class FaceEngineError(RuntimeError):
    pass


class FaceEnrollmentError(FaceEngineError):
    pass


@dataclass
class DetectedFace:
    bbox: tuple[int, int, int, int]  # top, right, bottom, left
    encoding: list[float]
    quality: float


@dataclass
class KnownFace:
    member_id: int
    member_name: str
    encoding: np.ndarray
    face_id: int


@dataclass
class FaceMatch:
    member_id: int
    member_name: str
    distance: float
    confidence: int
    face_id: int


@dataclass
class SearchMatch:
    member: object
    distance: float
    confidence: int
    face_path: str | None


_lock = threading.Lock()


class FaceEngine:
    @property
    def available(self) -> bool:
        return face_recognition is not None

    @property
    def error(self) -> str | None:
        return _IMPORT_ERROR

    def analyze(
        self,
        image_path: Path,
        *,
        detector: str | None = None,
        upsample: int | None = None,
        max_dimension: int | None = None,
    ) -> tuple[list[DetectedFace], int, int]:
        if not self.available:
            raise FaceEngineError(
                "Mesin pengenalan wajah tidak tersedia. Pastikan dlib dan face_recognition_models terpasang."
            )
        detector = detector or settings.face_detector
        upsample = settings.face_upsample if upsample is None else upsample
        max_dimension = max_dimension or settings.face_max_dimension

        try:
            pil = Image.open(image_path)
            pil.seek(0)
            original_width, original_height = pil.size
            if pil.mode != "RGB":
                pil = pil.convert("RGB")
            if max(pil.size) > max_dimension:
                scale = max_dimension / max(pil.size)
                pil = pil.resize(
                    (max(1, int(pil.width * scale)), max(1, int(pil.height * scale))),
                    Image.Resampling.LANCZOS,
                )
            image = np.ascontiguousarray(np.asarray(pil, dtype=np.uint8))
        except Exception as exc:
            raise FaceEngineError(f"Gambar tidak dapat dibaca oleh mesin wajah: {exc}") from exc

        with _lock:
            boxes = face_recognition.face_locations(
                image, number_of_times_to_upsample=upsample, model=detector
            )
            if not boxes:
                return [], original_width, original_height
            encodings = face_recognition.face_encodings(
                image, known_face_locations=boxes, num_jitters=1, model="small"
            )

        scale_x = original_width / image.shape[1]
        scale_y = original_height / image.shape[0]
        results: list[DetectedFace] = []
        for box, encoding in zip(boxes, encodings, strict=False):
            top, right, bottom, left = box
            width = right - left
            height = bottom - top
            if width < 40 or height < 40:
                continue
            scaled = (
                max(0, int(round(top * scale_y))),
                min(original_width, int(round(right * scale_x))),
                min(original_height, int(round(bottom * scale_y))),
                max(0, int(round(left * scale_x))),
            )
            quality = round(
                min(1.0, (width * height) / (min(image.shape[0], image.shape[1]) ** 2) * 6), 3
            )
            results.append(
                DetectedFace(bbox=scaled, encoding=[float(v) for v in encoding], quality=quality)
            )
        return results, original_width, original_height

    def detect_single(self, image_path: Path) -> DetectedFace:
        faces, _, _ = self.analyze(image_path)
        if not faces:
            raise FaceEnrollmentError(
                "Tidak ada wajah yang terdeteksi. Gunakan foto frontal dengan pencahayaan yang baik."
            )
        if len(faces) > 1:
            raise FaceEnrollmentError(
                f"Terdeteksi {len(faces)} wajah. Gunakan foto yang hanya berisi satu orang."
            )
        return faces[0]

    def known_faces(self, db: Session) -> list[KnownFace]:
        from ..models import Member, MemberFace

        rows = (
            db.query(MemberFace, Member)
            .join(Member, MemberFace.member_id == Member.id)
            .filter(Member.is_active.is_(True))
            .all()
        )
        known: list[KnownFace] = []
        for face, member in rows:
            if not face.encoding:
                continue
            known.append(
                KnownFace(
                    member_id=member.id,
                    member_name=member.full_name,
                    encoding=np.asarray(face.encoding, dtype=np.float64),
                    face_id=face.id,
                )
            )
        return known

    def known_login_faces(self, db: Session) -> list[KnownFace]:
        """Encoding wajah khusus login Face ID anggota dewan."""
        from ..models import Member, MemberFaceLogin

        rows = (
            db.query(MemberFaceLogin, Member)
            .join(Member, MemberFaceLogin.member_id == Member.id)
            .filter(Member.is_active.is_(True), MemberFaceLogin.is_active.is_(True))
            .all()
        )
        known: list[KnownFace] = []
        for face, member in rows:
            if not face.encoding:
                continue
            known.append(
                KnownFace(
                    member_id=member.id,
                    member_name=member.full_name,
                    encoding=np.asarray(face.encoding, dtype=np.float64),
                    face_id=face.id,
                )
            )
        return known

    def match(self, encoding: list[float] | np.ndarray, known: list[KnownFace]) -> list[FaceMatch]:
        if not known:
            return []
        matrix = np.vstack([item.encoding for item in known])
        target = np.asarray(encoding, dtype=np.float64)
        distances = np.linalg.norm(matrix - target, axis=1)
        best: dict[int, FaceMatch] = {}
        for item, distance in zip(known, distances, strict=False):
            value = float(distance)
            if item.member_id in best and best[item.member_id].distance <= value:
                continue
            best[item.member_id] = FaceMatch(
                member_id=item.member_id,
                member_name=item.member_name,
                distance=round(value, 4),
                confidence=confidence_from_distance(value),
                face_id=item.face_id,
            )
        return sorted(best.values(), key=lambda m: m.distance)

    def search(
        self, encoding: list[float], known: list[KnownFace], tolerance: float
    ) -> list[FaceMatch]:
        return [match for match in self.match(encoding, known) if match.distance <= tolerance]


def confidence_from_distance(distance: float | None) -> int:
    if distance is None:
        return 0
    return max(0, min(100, round((1.0 - distance) * 100)))


def auto_tag_distance() -> float:
    return settings.face_auto_tag


def review_distance() -> float:
    return settings.face_review


engine = FaceEngine()
