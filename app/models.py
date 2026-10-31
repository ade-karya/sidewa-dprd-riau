"""Model data SIDEWA."""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .constants import (
    PHOTO_PENDING,
    ROLE_STAF,
    STATUS_DRAFT,
)
from .database import Base


def utcnow() -> datetime:
    """Waktu UTC naive — aman untuk SQLite maupun PostgreSQL."""
    return datetime.now(UTC).replace(tzinfo=None)


activity_commissions = Table(
    "activity_commissions",
    Base.metadata,
    Column("activity_id", ForeignKey("activities.id", ondelete="CASCADE"), primary_key=True),
    Column("commission_id", ForeignKey("commissions.id", ondelete="CASCADE"), primary_key=True),
    Index("ix_activity_commissions_commission", "commission_id"),
)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )


class Commission(Base):
    __tablename__ = "commissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    bidang: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    color: Mapped[str] = mapped_column(String(20), default="#7E4890", nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    members: Mapped[list[Member]] = relationship(back_populates="commission")
    activities: Mapped[list[Activity]] = relationship(
        secondary=activity_commissions, back_populates="commissions"
    )

    @property
    def short_name(self) -> str:
        return f"Komisi {self.code}"


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(160), unique=True, nullable=True)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), default=ROLE_STAF, index=True, nullable=False)
    commission_id: Mapped[int | None] = mapped_column(
        ForeignKey("commissions.id", ondelete="SET NULL"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    avatar_path: Mapped[str | None] = mapped_column(String(255), nullable=True)

    commission: Mapped[Commission | None] = relationship()
    member_account: Mapped[MemberAccount | None] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    staff_account: Mapped[HumasStaffAccount | None] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    tokens: Mapped[list[ApiToken]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def initials(self) -> str:
        parts = [p for p in (self.full_name or self.username).split() if p]
        if not parts:
            return "?"
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[-1][0]).upper()


class Member(Base, TimestampMixin):
    __tablename__ = "members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(160), index=True, nullable=False)
    position: Mapped[str] = mapped_column(String(160), index=True, default="", nullable=False)
    commission_id: Mapped[int | None] = mapped_column(
        ForeignKey("commissions.id", ondelete="SET NULL"), index=True, nullable=True
    )
    party: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    dapil: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    email: Mapped[str | None] = mapped_column(String(160), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    bio: Mapped[str] = mapped_column(Text, default="", nullable=False)
    portrait_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True, nullable=False)
    consent_granted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    consent_note: Mapped[str] = mapped_column(String(255), default="", nullable=False)

    commission: Mapped[Commission | None] = relationship(back_populates="members")
    faces: Mapped[list[MemberFace]] = relationship(
        back_populates="member", cascade="all, delete-orphan", order_by="MemberFace.id"
    )
    face_logins: Mapped[list[MemberFaceLogin]] = relationship(
        back_populates="member", cascade="all, delete-orphan", order_by="MemberFaceLogin.id"
    )
    media_mentions: Mapped[list[MediaMention]] = relationship(
        back_populates="member", cascade="all, delete-orphan"
    )
    account: Mapped[MemberAccount | None] = relationship(
        back_populates="member", uselist=False, cascade="all, delete-orphan"
    )
    activity_links: Mapped[list[ActivityMember]] = relationship(
        back_populates="member", cascade="all, delete-orphan"
    )

    @property
    def initials(self) -> str:
        parts = [p for p in (self.full_name or "").split() if p]
        if not parts:
            return "?"
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[-1][0]).upper()


class MemberAccount(Base):
    """Penghubung akun login Face ID dengan data anggota dewan."""

    __tablename__ = "member_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    member_id: Mapped[int] = mapped_column(
        ForeignKey("members.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    last_face_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped[User] = relationship(back_populates="member_account")
    member: Mapped[Member] = relationship(back_populates="account")


class MemberFaceLogin(Base):
    """Encoding wajah yang dipakai khusus untuk login Face ID anggota."""

    __tablename__ = "member_face_logins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    member_id: Mapped[int] = mapped_column(
        ForeignKey("members.id", ondelete="CASCADE"), index=True, nullable=False
    )
    image_path: Mapped[str] = mapped_column(String(255), nullable=False)
    encoding: Mapped[list[float]] = mapped_column(JSON, nullable=False)
    quality: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    member: Mapped[Member] = relationship(back_populates="face_logins")


class HumasStaff(Base, TimestampMixin):
    """Staf Sekretariat DPRD yang bertugas di bagian Humas & Perpustakaan."""

    __tablename__ = "humas_staff"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    full_name: Mapped[str] = mapped_column(String(160), index=True, nullable=False)
    position: Mapped[str] = mapped_column(String(160), index=True, default="", nullable=False)
    unit: Mapped[str] = mapped_column(
        String(160), default="Bagian Humas & Perpustakaan", nullable=False
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    email: Mapped[str | None] = mapped_column(String(160), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    bio: Mapped[str] = mapped_column(Text, default="", nullable=False)
    portrait_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True, nullable=False)
    consent_granted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    consent_note: Mapped[str] = mapped_column(String(255), default="", nullable=False)

    faces: Mapped[list[HumasStaffFaceLogin]] = relationship(
        back_populates="staff", cascade="all, delete-orphan", order_by="HumasStaffFaceLogin.id"
    )
    account: Mapped[HumasStaffAccount | None] = relationship(
        back_populates="staff", uselist=False, cascade="all, delete-orphan"
    )

    @property
    def initials(self) -> str:
        parts = [p for p in (self.full_name or "").split() if p]
        if not parts:
            return "?"
        if len(parts) == 1:
            return parts[0][:2].upper()
        return (parts[0][0] + parts[-1][0]).upper()


class HumasStaffAccount(Base):
    """Penghubung akun login Face ID dengan data staf Humas."""

    __tablename__ = "humas_staff_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    staff_id: Mapped[int] = mapped_column(
        ForeignKey("humas_staff.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    last_face_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped[User] = relationship(back_populates="staff_account")
    staff: Mapped[HumasStaff] = relationship(back_populates="account")


class HumasStaffFaceLogin(Base):
    """Encoding wajah khusus login Face ID staf Humas."""

    __tablename__ = "humas_staff_face_logins"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    staff_id: Mapped[int] = mapped_column(
        ForeignKey("humas_staff.id", ondelete="CASCADE"), index=True, nullable=False
    )
    image_path: Mapped[str] = mapped_column(String(255), nullable=False)
    encoding: Mapped[list[float]] = mapped_column(JSON, nullable=False)
    quality: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    staff: Mapped[HumasStaff] = relationship(back_populates="faces")


class AiPhotoSettings(Base, TimestampMixin):
    """Preferensi AI per pengguna untuk seleksi foto Humas.

    Kunci API disimpan dalam bentuk terenkripsi (lihat ``services.keyvault``)
    dan tidak pernah dikirim balik ke peramban.
    """

    __tablename__ = "ai_photo_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    api_key_encrypted: Mapped[str] = mapped_column(Text, default="", nullable=False)
    api_key_hint: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    model: Mapped[str] = mapped_column(
        String(80), default="gemini-3.5-flash-lite", nullable=False
    )
    rpm: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    rpd: Mapped[int] = mapped_column(Integer, default=500, nullable=False)
    tpm: Mapped[int] = mapped_column(Integer, default=250000, nullable=False)
    preferred_notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    default_skill_key: Mapped[str] = mapped_column(
        String(60), default="jurnalistik", nullable=False
    )
    auto_learn: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    learned_preferences: Mapped[str] = mapped_column(Text, default="", nullable=False)
    learned_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    key_verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    key_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    user: Mapped[User] = relationship()


class PhotoSelectionSkill(Base, TimestampMixin):
    """Skill kurasi foto buatan pengguna (preset bawaan ada di kode)."""

    __tablename__ = "photo_selection_skills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    icon: Mapped[str] = mapped_column(String(30), default="sparkles", nullable=False)
    description: Mapped[str] = mapped_column(String(220), default="", nullable=False)
    instructions: Mapped[str] = mapped_column(Text, default="", nullable=False)
    target_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    min_score: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    auto_update: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    learned_preferences: Mapped[str] = mapped_column(Text, default="", nullable=False)
    auto_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_shared: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    share_usage_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    user: Mapped[User] = relationship()

    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_photo_skill_user_name"),
    )


class PhotoSelectionRun(Base):
    """Satu sesi kurasi foto oleh agen AI."""

    __tablename__ = "photo_selection_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    skill_key: Mapped[str] = mapped_column(String(60), default="jurnalistik", nullable=False)
    skill_name: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    skill_instructions: Mapped[str] = mapped_column(Text, default="", nullable=False)
    skill_learned_preferences: Mapped[str] = mapped_column(Text, default="", nullable=False)
    learned_preferences: Mapped[str] = mapped_column(Text, default="", nullable=False)
    user_notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    model: Mapped[str] = mapped_column(
        String(80), default="gemini-3.5-flash-lite", nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(20), default="queued", index=True, nullable=False
    )
    target_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    min_score: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    total_items: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    processed_items: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    selected_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    backup_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rejected_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    quota_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tokens_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    activity_id: Mapped[int | None] = mapped_column(
        ForeignKey("activities.id", ondelete="SET NULL"), nullable=True
    )
    applied_activity_id: Mapped[int | None] = mapped_column(
        ForeignKey("activities.id", ondelete="SET NULL"), nullable=True
    )
    applied_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    next_request_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped[User] = relationship(foreign_keys=[user_id])
    activity: Mapped[Activity | None] = relationship(foreign_keys=[activity_id])
    applied_activity: Mapped[Activity | None] = relationship(
        foreign_keys=[applied_activity_id]
    )
    items: Mapped[list[PhotoSelectionItem]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="PhotoSelectionItem.position",
    )


class PhotoSelectionItem(Base):
    """Satu foto di dalam sesi kurasi AI."""

    __tablename__ = "photo_selection_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("photo_selection_runs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    file_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    thumb_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    width: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    height: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    perceptual_hash: Mapped[str] = mapped_column(String(16), default="", nullable=False)
    technical: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    verdict: Mapped[str] = mapped_column(
        String(16), default="pending", index=True, nullable=False
    )
    ai_verdict: Mapped[str] = mapped_column(String(16), default="", nullable=False)
    manual_override: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reason: Mapped[str] = mapped_column(String(300), default="", nullable=False)
    caption: Mapped[str] = mapped_column(String(180), default="", nullable=False)
    tags: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    strengths: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    weaknesses: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    face_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duplicate_of_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    applied_photo_id: Mapped[int | None] = mapped_column(
        ForeignKey("activity_photos.id", ondelete="SET NULL"), nullable=True
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    run: Mapped[PhotoSelectionRun] = relationship(back_populates="items")

    __table_args__ = (
        Index("ix_photo_selection_item_run_verdict", "run_id", "verdict"),
    )


class AiRequestLog(Base):
    """Jejak permintaan ke API AI, dipakai untuk menegakkan RPM/RPD."""

    __tablename__ = "ai_request_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    run_id: Mapped[int | None] = mapped_column(
        ForeignKey("photo_selection_runs.id", ondelete="SET NULL"), nullable=True
    )
    model: Mapped[str] = mapped_column(String(80), default="", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, index=True, nullable=False
    )

    __table_args__ = (
        Index("ix_ai_request_user_created", "user_id", "created_at"),
    )


class SentimentRun(Base):
    """Riwayat pemindaian sentimen media online melalui Tavily."""

    __tablename__ = "sentiment_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    member_id: Mapped[int] = mapped_column(
        ForeignKey("members.id", ondelete="CASCADE"), index=True, nullable=False
    )
    query: Mapped[str] = mapped_column(String(400), default="", nullable=False)
    requested_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), default="success", nullable=False)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    result_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    positive_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    neutral_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    negative_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    average_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, index=True, nullable=False
    )

    member: Mapped[Member] = relationship()
    requested_by: Mapped[User | None] = relationship()


class MediaMention(Base):
    """Satu pemberitaan media online tentang anggota dewan."""

    __tablename__ = "media_mentions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    member_id: Mapped[int] = mapped_column(
        ForeignKey("members.id", ondelete="CASCADE"), index=True, nullable=False
    )
    run_id: Mapped[int | None] = mapped_column(
        ForeignKey("sentiment_runs.id", ondelete="SET NULL"), index=True, nullable=True
    )
    title: Mapped[str] = mapped_column(String(400), default="", nullable=False)
    url: Mapped[str] = mapped_column(Text, default="", nullable=False)
    url_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    snippet: Mapped[str] = mapped_column(Text, default="", nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sentiment: Mapped[str] = mapped_column(
        String(20), default="netral", index=True, nullable=False
    )
    sentiment_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    keywords: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    provider: Mapped[str] = mapped_column(String(30), default="tavily", nullable=False)
    fetched_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, index=True, nullable=False
    )

    member: Mapped[Member] = relationship(back_populates="media_mentions")
    run: Mapped[SentimentRun | None] = relationship()
    fetched_by: Mapped[User | None] = relationship()

    __table_args__ = (
        UniqueConstraint("member_id", "url_hash", name="uq_media_mention_member_url"),
    )


class MemberFace(Base):
    __tablename__ = "member_faces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    member_id: Mapped[int] = mapped_column(
        ForeignKey("members.id", ondelete="CASCADE"), index=True, nullable=False
    )
    image_path: Mapped[str] = mapped_column(String(255), nullable=False)
    encoding: Mapped[list[float]] = mapped_column(JSON, nullable=False)
    quality: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source: Mapped[str] = mapped_column(String(40), default="upload", nullable=False)
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    member: Mapped[Member] = relationship(back_populates="faces")


class Activity(Base, TimestampMixin):
    __tablename__ = "activities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    category: Mapped[str] = mapped_column(String(80), default="Lainnya", index=True, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default=STATUS_DRAFT, index=True, nullable=False
    )
    activity_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    start_time: Mapped[str | None] = mapped_column(String(5), nullable=True)
    end_time: Mapped[str | None] = mapped_column(String(5), nullable=True)
    location_name: Mapped[str] = mapped_column(String(200), index=True, default="", nullable=False)
    location_address: Mapped[str] = mapped_column(String(400), default="", nullable=False)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    commission_id: Mapped[int | None] = mapped_column(
        ForeignKey("commissions.id", ondelete="SET NULL"), index=True, nullable=True
    )
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    view_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    commission: Mapped[Commission | None] = relationship(foreign_keys=[commission_id])
    commissions: Mapped[list[Commission]] = relationship(
        secondary=activity_commissions, back_populates="activities"
    )
    creator: Mapped[User | None] = relationship(foreign_keys=[created_by_id])
    photos: Mapped[list[ActivityPhoto]] = relationship(
        back_populates="activity",
        cascade="all, delete-orphan",
        order_by="ActivityPhoto.sort_order",
    )
    member_links: Mapped[list[ActivityMember]] = relationship(
        back_populates="activity", cascade="all, delete-orphan"
    )
    detections: Mapped[list[FaceDetection]] = relationship(
        "FaceDetection",
        secondary="activity_photos",
        primaryjoin="Activity.id == ActivityPhoto.activity_id",
        secondaryjoin="FaceDetection.photo_id == ActivityPhoto.id",
        viewonly=True,
        order_by="FaceDetection.id",
    )
    press_releases: Mapped[list[PressRelease]] = relationship(
        back_populates="activity", order_by="PressRelease.release_date.desc()"
    )

    __table_args__ = (Index("ix_activities_date_status", "activity_date", "status"),)

    @property
    def cover(self) -> ActivityPhoto | None:
        ready = [p for p in self.photos if p.thumb_path]
        return ready[0] if ready else (self.photos[0] if self.photos else None)

    @property
    def members(self) -> list[Member]:
        return [link.member for link in self.member_links if link.member and link.confirmed]

    @property
    def confirmed_member_count(self) -> int:
        return len([link for link in self.member_links if link.confirmed])

    @property
    def all_commission_ids(self) -> list[int]:
        ids = {c.id for c in self.commissions}
        if self.commission_id:
            ids.add(self.commission_id)
        return sorted(ids)


class PressRelease(Base, TimestampMixin):
    """Siaran pers (rilis) Humas yang dapat ditautkan ke kegiatan."""

    __tablename__ = "press_releases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(200), unique=True, index=True, nullable=False)
    summary: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default=STATUS_DRAFT, index=True, nullable=False
    )
    release_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    activity_id: Mapped[int | None] = mapped_column(
        ForeignKey("activities.id", ondelete="SET NULL"), index=True, nullable=True
    )
    author_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    view_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tags: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    activity: Mapped[Activity | None] = relationship(back_populates="press_releases")
    author: Mapped[User | None] = relationship()

    @property
    def tag_list(self) -> list[str]:
        return [str(tag) for tag in (self.tags or []) if str(tag).strip()]

    @property
    def reading_minutes(self) -> int:
        words = len((self.body or "").split())
        return max(1, round(words / 200))

    __table_args__ = (
        Index("ix_press_releases_date_status", "release_date", "status"),
    )


class ReleaseSkill(Base, TimestampMixin):
    """Satu skill bersama untuk gaya penulisan rilis Humas.

    Skill ini tidak dimiliki satu pengguna. Isinya diperbarui otomatis dari
    kumpulan rilis yang sedang terbit, sehingga panduan gaya selalu mengikuti
    publikasi terbaru tim Humas.
    """

    __tablename__ = "release_skills"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(
        String(60), unique=True, index=True, default="gaya-rilis-humas", nullable=False
    )
    name: Mapped[str] = mapped_column(
        String(80), default="Gaya Rilis Humas", nullable=False
    )
    description: Mapped[str] = mapped_column(String(220), default="", nullable=False)
    instructions: Mapped[str] = mapped_column(Text, default="", nullable=False)
    learned_preferences: Mapped[str] = mapped_column(Text, default="", nullable=False)
    source_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    auto_update: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    auto_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_shared: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ActivityPhoto(Base):
    __tablename__ = "activity_photos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    activity_id: Mapped[int] = mapped_column(
        ForeignKey("activities.id", ondelete="CASCADE"), index=True, nullable=False
    )
    file_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    thumb_path: Mapped[str | None] = mapped_column(String(255), nullable=True)
    width: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    height: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    caption: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default=PHOTO_PENDING, index=True, nullable=False
    )
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    face_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    uploaded_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    activity: Mapped[Activity] = relationship(back_populates="photos")
    detections: Mapped[list[FaceDetection]] = relationship(
        back_populates="photo",
        cascade="all, delete-orphan",
        order_by="FaceDetection.id",
    )


class FaceDetection(Base):
    __tablename__ = "face_detections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    photo_id: Mapped[int] = mapped_column(
        ForeignKey("activity_photos.id", ondelete="CASCADE"), index=True, nullable=False
    )
    member_id: Mapped[int | None] = mapped_column(
        ForeignKey("members.id", ondelete="SET NULL"), index=True, nullable=True
    )
    bbox_top: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    bbox_right: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    bbox_bottom: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    bbox_left: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    encoding: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)
    distance: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_rejected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    photo: Mapped[ActivityPhoto] = relationship(back_populates="detections")
    member: Mapped[Member | None] = relationship()

    @property
    def label(self) -> str:
        if self.is_rejected:
            return "Ditolak"
        if self.member:
            return self.member.full_name
        return "Wajah belum dikenali"


class ActivityMember(Base):
    __tablename__ = "activity_members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    activity_id: Mapped[int] = mapped_column(
        ForeignKey("activities.id", ondelete="CASCADE"), index=True, nullable=False
    )
    member_id: Mapped[int] = mapped_column(
        ForeignKey("members.id", ondelete="CASCADE"), index=True, nullable=False
    )
    source: Mapped[str] = mapped_column(String(20), default="auto", nullable=False)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    added_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    activity: Mapped[Activity] = relationship(back_populates="member_links")
    member: Mapped[Member] = relationship(back_populates="activity_links")

    __table_args__ = (UniqueConstraint("activity_id", "member_id", name="uq_activity_member"),)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    actor_name: Mapped[str] = mapped_column(String(160), default="Sistem", nullable=False)
    action: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    summary: Mapped[str] = mapped_column(String(400), default="", nullable=False)
    detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, index=True, nullable=False
    )

    actor: Mapped[User | None] = relationship()


class ApiToken(Base):
    __tablename__ = "api_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), default="Token integrasi", nullable=False)
    prefix: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    user: Mapped[User] = relationship(back_populates="tokens")
