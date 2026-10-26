"""Pencarian dan filter dokumentasi kegiatan."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import or_
from sqlalchemy.orm import Query, Session

from ..config import settings
from ..constants import CONTENT_MANAGER_ROLES, STATUS_PUBLISHED
from ..models import Activity, ActivityMember, Commission, Member, User
from . import face_engine


@dataclass
class Page:
    items: list
    total: int
    page: int
    per_page: int

    @property
    def pages(self) -> int:
        return max(1, (self.total + self.per_page - 1) // self.per_page)

    @property
    def has_prev(self) -> bool:
        return self.page > 1

    @property
    def has_next(self) -> bool:
        return self.page < self.pages

    @property
    def start(self) -> int:
        return (self.page - 1) * self.per_page + 1 if self.total else 0

    @property
    def end(self) -> int:
        return min(self.page * self.per_page, self.total)


@dataclass
class FaceSearchResult:
    query_faces: int = 0
    matches: list = field(default_factory=list)  # list[SearchMatch + Member]
    unknown_faces: int = 0
    error: str | None = None


def visible_query(db: Session, user: User) -> Query:
    query = db.query(Activity)
    if user.role not in CONTENT_MANAGER_ROLES:
        query = query.filter(Activity.status == STATUS_PUBLISHED)
    return query


def apply_filters(
    query: Query,
    *,
    q: str | None = None,
    commission: str | None = None,
    category: str | None = None,
    location: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    member_id: int | None = None,
    status: str | None = None,
    face_member_ids: list[int] | None = None,
) -> Query:
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(
            or_(
                Activity.title.ilike(like),
                Activity.description.ilike(like),
                Activity.location_name.ilike(like),
                Activity.location_address.ilike(like),
                Activity.category.ilike(like),
                Activity.code.ilike(like),
                Activity.commissions.any(Commission.name.ilike(like)),
                Activity.commissions.any(Commission.bidang.ilike(like)),
                Activity.member_links.any(
                    ActivityMember.member.has(
                        or_(Member.full_name.ilike(like), Member.position.ilike(like))
                    )
                ),
            )
        )
    if commission:
        query = query.filter(Activity.commissions.any(Commission.code == commission))
    if category:
        query = query.filter(Activity.category == category)
    if location:
        like = f"%{location.strip()}%"
        query = query.filter(
            or_(Activity.location_name.ilike(like), Activity.location_address.ilike(like))
        )
    if date_from:
        query = query.filter(Activity.activity_date >= date_from)
    if date_to:
        query = query.filter(Activity.activity_date <= date_to)
    if member_id:
        query = query.filter(Activity.member_links.any(ActivityMember.member_id == member_id))
    if status:
        query = query.filter(Activity.status == status)
    if face_member_ids is not None:
        if not face_member_ids:
            query = query.filter(Activity.id < 0)
        else:
            query = query.filter(
                Activity.member_links.any(ActivityMember.member_id.in_(face_member_ids))
            )
    return query


def paginate(query: Query, page: int, per_page: int) -> Page:
    page = max(1, page)
    total = query.order_by(None).count()
    items = query.offset((page - 1) * per_page).limit(per_page).all()
    return Page(items=items, total=total, page=page, per_page=per_page)


def search_by_face(
    db: Session,
    image_path,
    *,
    tolerance: float | None = None,
) -> FaceSearchResult:
    tolerance = tolerance or 0.60
    if not face_engine.engine.available:
        return FaceSearchResult(error="Mesin pengenalan wajah tidak tersedia di server.")
    try:
        faces, _, _ = face_engine.engine.analyze(image_path)
    except face_engine.FaceEngineError as exc:
        return FaceSearchResult(error=str(exc))
    if not faces:
        return FaceSearchResult(
            error="Tidak ada wajah yang terdeteksi pada foto pencarian. Gunakan foto frontal yang jelas."
        )

    known = face_engine.engine.known_faces(db)
    if not known:
        return FaceSearchResult(
            query_faces=len(faces),
            error="Belum ada data wajah anggota yang terdaftar. Hubungi administrator.",
        )

    # Untuk setiap wajah pada foto, ambil kandidat terbaik dan hanya sertakan
    # kandidat lain yang jaraknya berdekatan. Ini menekan positif palsu pada
    # foto grup tanpa mengorbankan wajah lain yang memang hadir.
    found: dict[int, face_engine.FaceMatch] = {}
    recognized_faces = 0
    margin = max(0.02, settings.face_match_margin)
    for detected in faces:
        candidates = face_engine.engine.search(detected.encoding, known, tolerance)
        if not candidates:
            continue
        recognized_faces += 1
        best = candidates[0]
        cutoff = best.distance + margin
        for match in candidates:
            if match.distance > cutoff:
                continue
            current = found.get(match.member_id)
            if current is None or match.distance < current.distance:
                found[match.member_id] = match

    members = {}
    if found:
        members = {
            member.id: member
            for member in db.query(Member).filter(Member.id.in_(list(found.keys()))).all()
        }

    matches = []
    for member_id, match in sorted(found.items(), key=lambda item: item[1].distance):
        member = members.get(member_id)
        if not member:
            continue
        face = next((f for f in member.faces if f.id == match.face_id), None)
        matches.append(
            {
                "member": member,
                "distance": match.distance,
                "confidence": match.confidence,
                "face_path": face.image_path if face else member.portrait_path,
            }
        )
    return FaceSearchResult(
        query_faces=len(faces),
        matches=matches,
        unknown_faces=max(0, len(faces) - recognized_faces),
    )
