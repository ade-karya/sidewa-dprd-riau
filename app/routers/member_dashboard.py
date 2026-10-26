"""Dashboard pribadi anggota dewan dan pemindaian sentimen media online."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..audit import audit
from ..config import settings
from ..constants import (
    ALL_ROLES,
    ROLE_ADMIN,
    ROLE_ANGGOTA,
    ROLE_STAF,
    ROLE_SUPERADMIN,
    SENTIMENT_ROLES,
)
from ..database import get_db
from ..deps import csrf_protect, flash, require_roles, require_user
from ..models import (
    Commission,
    MediaMention,
    Member,
    MemberAccount,
    User,
)
from ..services import media_monitor, tavily
from ..services.member_analytics import (
    SENTIMENT_LABELS,
    SENTIMENT_TONES,
    member_dashboard_data,
    member_sentiment_summary,
    sentiment_overview,
)
from ..services.search import Page, paginate
from ..templating import render

router = APIRouter(dependencies=[Depends(csrf_protect)])

SENTIMENT_ACCESS = require_roles(*SENTIMENT_ROLES)


def _member_or_404(db: Session, member_id: int) -> Member:
    member = db.get(Member, member_id)
    if not member:
        raise HTTPException(status_code=404, detail="Anggota tidak ditemukan.")
    return member


def _account_for_user(db: Session, user: User) -> MemberAccount | None:
    return db.query(MemberAccount).filter(MemberAccount.user_id == user.id).first()


def _ensure_can_view(db: Session, user: User, member: Member) -> None:
    if user.role == ROLE_ANGGOTA:
        account = _account_for_user(db, user)
        if not account or account.member_id != member.id:
            raise HTTPException(
                status_code=403,
                detail="Anda hanya dapat membuka dashboard anggota milik sendiri.",
            )
        return
    if user.role not in ALL_ROLES:
        raise HTTPException(status_code=403, detail="Akses ditolak.")


def _can_search_sentiment(user: User, member: Member) -> bool:
    if user.role in {ROLE_SUPERADMIN, ROLE_ADMIN}:
        return True
    if user.role == ROLE_STAF:
        return bool(
            user.commission_id
            and member.commission_id
            and user.commission_id == member.commission_id
        )
    return False


def _commissions(db: Session) -> list[Commission]:
    return (
        db.query(Commission)
        .filter(Commission.is_active.is_(True))
        .order_by(Commission.sort_order, Commission.code)
        .all()
    )


@router.get("/dashboard-anggota")
def my_member_dashboard(
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    if user.role == ROLE_ANGGOTA:
        account = _account_for_user(db, user)
        if not account:
            raise HTTPException(
                status_code=403,
                detail="Akun ini belum terhubung dengan data anggota dewan.",
            )
        return RedirectResponse(f"/dashboard-anggota/{account.member_id}", status_code=303)
    return RedirectResponse("/anggota", status_code=303)


@router.get("/dashboard-anggota/{member_id}")
def member_dashboard(
    member_id: int,
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    member = _member_or_404(db, member_id)
    _ensure_can_view(db, user, member)
    data = member_dashboard_data(db, member, user)
    return render(
        request,
        "members/dashboard.html",
        user=user,
        member=member,
        data=data,
        sentiment=data["sentiment"],
        sentiment_labels=SENTIMENT_LABELS,
        sentiment_tones=SENTIMENT_TONES,
        can_search_sentiment=_can_search_sentiment(user, member),
        tavily_configured=settings.tavily_configured,
    )


@router.get("/anggota/{member_id}/sentimen")
def member_sentiment_list(
    member_id: int,
    request: Request,
    tone: str = "",
    q: str = "",
    page: int = 1,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    member = _member_or_404(db, member_id)
    _ensure_can_view(db, user, member)
    query = db.query(MediaMention).filter(MediaMention.member_id == member.id)
    if tone in SENTIMENT_LABELS:
        query = query.filter(MediaMention.sentiment == tone)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(
            or_(
                MediaMention.title.ilike(like),
                MediaMention.snippet.ilike(like),
                MediaMention.source.ilike(like),
            )
        )
    query = query.order_by(
        MediaMention.published_at.desc().nullslast(), MediaMention.id.desc()
    )
    result: Page = paginate(query, page, 12)
    summary = member_sentiment_summary(db, member, limit=0)
    return render(
        request,
        "members/sentiment.html",
        user=user,
        member=member,
        result=result,
        summary=summary,
        tone=tone,
        q=q,
        sentiment_labels=SENTIMENT_LABELS,
        sentiment_tones=SENTIMENT_TONES,
        can_search_sentiment=_can_search_sentiment(user, member),
        tavily_configured=settings.tavily_configured,
    )


@router.get("/sentimen")
def sentiment_overview_page(
    request: Request,
    q: str = "",
    commission: str = "",
    page: int = 1,
    user: User = Depends(SENTIMENT_ACCESS),
    db: Session = Depends(get_db),
):
    query = db.query(Member).filter(Member.is_active.is_(True))
    if user.role == ROLE_STAF:
        if not user.commission_id:
            query = query.filter(Member.id < 0)
        else:
            query = query.filter(Member.commission_id == user.commission_id)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(
            or_(
                Member.full_name.ilike(like),
                Member.position.ilike(like),
                Member.party.ilike(like),
                Member.dapil.ilike(like),
            )
        )
    if commission:
        query = query.join(Commission, Member.commission_id == Commission.id).filter(
            Commission.code == commission
        )
    query = query.order_by(Member.commission_id.is_(None), Member.full_name)
    result: Page = paginate(query, page, 15)
    rows = sentiment_overview(db, result.items)
    return render(
        request,
        "sentiment/overview.html",
        user=user,
        result=result,
        rows=rows,
        commissions=_commissions(db),
        q=q,
        commission=commission,
        tavily_configured=settings.tavily_configured,
        sentiment_labels=SENTIMENT_LABELS,
        sentiment_tones=SENTIMENT_TONES,
    )


def _run_sentiment_for_member(
    request: Request,
    member: Member,
    user: User,
    db: Session,
    *,
    redirect_to: str,
) -> RedirectResponse:
    if not _can_search_sentiment(user, member):
        raise HTTPException(
            status_code=403,
            detail="Anda tidak berwenang memindai sentimen anggota ini.",
        )
    try:
        run = media_monitor.run_member_sentiment(db, member, actor=user)
    except tavily.TavilyError as exc:
        audit(
            db,
            request,
            "SENTIMENT_SEARCH_FAILED",
            actor=user,
            entity_type="member",
            entity_id=member.id,
            summary=f"Pemindaian sentimen {member.full_name} gagal",
            detail={"error": str(exc)},
        )
        db.commit()
        flash(request, f"Pemindaian sentimen gagal: {exc}", "danger")
        return RedirectResponse(redirect_to, status_code=303)

    audit(
        db,
        request,
        "SENTIMENT_SEARCH",
        actor=user,
        entity_type="member",
        entity_id=member.id,
        summary=(
            f"Memindai {run.result_count} pemberitaan tentang {member.full_name} "
            f"melalui Tavily"
        ),
        detail={
            "positive": run.positive_count,
            "neutral": run.neutral_count,
            "negative": run.negative_count,
            "average_score": run.average_score,
        },
    )
    db.commit()
    if run.result_count:
        flash(
            request,
            f"Pemindaian selesai: {run.result_count} pemberitaan ditemukan "
            f"({run.positive_count} positif, {run.neutral_count} netral, "
            f"{run.negative_count} negatif).",
            "success",
        )
    else:
        flash(
            request,
            "Pemindaian selesai, tetapi tidak ada pemberitaan baru yang ditemukan.",
            "warning",
        )
    return RedirectResponse(redirect_to, status_code=303)


@router.post("/anggota/{member_id}/sentimen/cari")
def search_member_sentiment(
    member_id: int,
    request: Request,
    user: User = Depends(SENTIMENT_ACCESS),
    db: Session = Depends(get_db),
):
    member = _member_or_404(db, member_id)
    return _run_sentiment_for_member(
        request,
        member,
        user,
        db,
        redirect_to=f"/dashboard-anggota/{member.id}#sentimen",
    )


@router.post("/sentimen/{member_id}/cari")
def search_member_sentiment_from_overview(
    member_id: int,
    request: Request,
    user: User = Depends(SENTIMENT_ACCESS),
    db: Session = Depends(get_db),
):
    member = _member_or_404(db, member_id)
    return _run_sentiment_for_member(
        request,
        member,
        user,
        db,
        redirect_to=f"/dashboard-anggota/{member.id}#sentimen",
    )
