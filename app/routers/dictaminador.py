from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import case
from datetime import datetime, date
from typing import List, Optional
from pydantic import BaseModel

from app.db.session import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.chapter import Chapter
from app.models.book import Book
from app.models.chapter_deadline import ChapterDeadline

router = APIRouter(prefix="/dictaminador", tags=["dictaminador"])

# =========================
# Schemas
# =========================
class DictaminadorChapterOut(BaseModel):
    id: int
    title: str
    status: str
    updated_at: str
    file_path: Optional[str] = None
    book_name: Optional[str] = None
    author_name: Optional[str] = None
    author_email: Optional[str] = None

    # Editorial -> Dictaminador
    deadline_at: Optional[str] = None
    deadline_stage: Optional[str] = None
    days_remaining: Optional[int] = None
    is_overdue: Optional[bool] = False

    # Dictaminador -> Autor
    author_deadline_at: Optional[str] = None
    author_deadline_set_at: Optional[str] = None
    author_deadline_set_by: Optional[int] = None

    class Config:
        from_attributes = True

class StatusUpdateIn(BaseModel):
    status: str
    comment: Optional[str] = None

class AuthorDeadlineIn(BaseModel):
    author_deadline_at: str  # "YYYY-MM-DD"
    note: Optional[str] = None

# =========================
# Helpers
# =========================
def _user_id(db: Session, user_or_payload) -> int:
    if not isinstance(user_or_payload, dict):
        return int(user_or_payload.id)

    if user_or_payload.get("id") is not None:
        return int(user_or_payload["id"])
    if user_or_payload.get("user_id") is not None:
        return int(user_or_payload["user_id"])

    sub = user_or_payload.get("sub")
    if isinstance(sub, int):
        return int(sub)
    if isinstance(sub, str) and sub.isdigit():
        return int(sub)

    if isinstance(sub, str) and "@" in sub:
        u = db.query(User).filter(User.email == sub.strip().lower()).first()
        if not u:
            raise HTTPException(status_code=401, detail="Usuario no encontrado")
        return int(u.id)

    raise HTTPException(status_code=401, detail="Token inválido")

def _require_dictaminador(db: Session, user_or_payload) -> User:
    uid = _user_id(db, user_or_payload)
    me = db.query(User).filter(User.id == uid).first()
    if not me:
        raise HTTPException(status_code=401, detail="Usuario no encontrado")
    if me.role != "dictaminador":
        raise HTTPException(status_code=403, detail="No autorizado (solo dictaminador)")
    return me

def _deadline_meta(deadline_at_val):
    """days_remaining, is_overdue"""
    if not deadline_at_val:
        return None, False

    today = date.today()

    if isinstance(deadline_at_val, datetime):
        d = deadline_at_val.date()
    else:
        d = deadline_at_val  # date

    days = (d - today).days
    return days, (days < 0)

# =========================
# GET /dictaminador/chapters
# =========================
@router.get("/chapters", response_model=List[DictaminadorChapterOut])
def list_my_chapters(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    dictaminador = _require_dictaminador(db, user)

    chapters = (
        db.query(
            Chapter.id,
            Chapter.title,
            Chapter.status,
            Chapter.updated_at,
            Chapter.file_path,
            Book.name.label("book_name"),
            Chapter.author_name,
            Chapter.author_email,

            Chapter.deadline_at,
            Chapter.deadline_stage,

            Chapter.author_deadline_at,
            Chapter.author_deadline_set_at,
            Chapter.author_deadline_set_by,
        )
        .join(Book, Book.id == Chapter.book_id)
        .filter(Chapter.evaluator_id == dictaminador.id)
        # ✅ FIX MySQL: NO usar NULLS LAST
        .order_by(
            case((Chapter.deadline_at.is_(None), 1), else_=0).asc(),
            Chapter.deadline_at.asc(),
            Chapter.updated_at.desc(),
        )
        .all()
    )

    result: List[DictaminadorChapterOut] = []
    for c in chapters:
        days_remaining, is_overdue = _deadline_meta(c.deadline_at)

        result.append(
            DictaminadorChapterOut(
                id=int(c.id),
                title=c.title,
                status=str(c.status),
                updated_at=c.updated_at.isoformat() if c.updated_at else "",
                file_path=c.file_path,
                book_name=c.book_name,
                author_name=c.author_name,
                author_email=c.author_email,

                deadline_at=c.deadline_at.isoformat() if c.deadline_at else None,
                deadline_stage=c.deadline_stage,
                days_remaining=days_remaining,
                is_overdue=is_overdue,

                author_deadline_at=c.author_deadline_at.isoformat() if c.author_deadline_at else None,
                author_deadline_set_at=c.author_deadline_set_at.isoformat() if c.author_deadline_set_at else None,
                author_deadline_set_by=int(c.author_deadline_set_by) if c.author_deadline_set_by else None,
            )
        )

    return result

# =========================
# POST /dictaminador/chapters/{chapter_id}/author-deadline
# =========================
@router.post("/chapters/{chapter_id}/author-deadline")
def set_author_deadline(
    chapter_id: int,
    payload: AuthorDeadlineIn,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    dictaminador = _require_dictaminador(db, user)

    chapter = (
        db.query(Chapter)
        .filter(Chapter.id == chapter_id, Chapter.evaluator_id == dictaminador.id)
        .first()
    )
    if not chapter:
        raise HTTPException(status_code=404, detail="Capítulo no encontrado")

    if chapter.status not in ("CORRECCIONES", "CORRECCIONES_SOLICITADAS_A_AUTOR"):
        raise HTTPException(
            status_code=400,
            detail="Solo puedes fijar fecha límite al autor cuando el capítulo esté en correcciones",
        )

    try:
        deadline_date = datetime.strptime(payload.author_deadline_at, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato de fecha inválido. Use YYYY-MM-DD")

    chapter.author_deadline_at = deadline_date
    chapter.author_deadline_set_at = datetime.utcnow()
    chapter.author_deadline_set_by = int(dictaminador.id)
    chapter.updated_at = datetime.utcnow()

    db.add(
        ChapterDeadline(
            chapter_id=int(chapter.id),
            stage="AUTOR_CORRECCIONES",
            due_at=deadline_date,
            set_by=int(dictaminador.id),
            note=payload.note,
        )
    )

    db.add(chapter)
    db.commit()
    db.refresh(chapter)

    return {"ok": True, "author_deadline_at": chapter.author_deadline_at.isoformat()}