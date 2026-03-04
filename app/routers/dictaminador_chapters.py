# app/routers/dictaminador_chapters.py
import os
from datetime import datetime, date
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.db.session import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.book import Book
from app.models.chapter import Chapter
from app.models.chapter_deadline import ChapterDeadline

router = APIRouter(prefix="/dictaminador", tags=["dictaminador"])

# =========================
# Schemas
# =========================
class DictChapterOut(BaseModel):
    id: int
    title: str
    status: str
    updated_at: str

    book_name: Optional[str] = None
    author_name: Optional[str] = None
    author_email: Optional[str] = None

    file_path: Optional[str] = None
    corrected_file_path: Optional[str] = None
    corrected_updated_at: Optional[str] = None

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
# Helpers auth
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
    if str(me.role).lower() != "dictaminador":
        raise HTTPException(status_code=403, detail="No autorizado (solo dictaminador)")
    return me


# =========================
# Helpers deadlines
# =========================
def _deadline_meta(deadline_at_val) -> tuple[Optional[int], bool]:
    if not deadline_at_val:
        return None, False
    today = date.today()
    d = deadline_at_val.date() if isinstance(deadline_at_val, datetime) else deadline_at_val
    days = (d - today).days
    return days, (days < 0)


# =========================
# Helpers archivos (para /api/storage/...)
# =========================
STORAGE_DIR = os.getenv("STORAGE_DIR", "storage")

def _physical_from_storage_url(file_url: str) -> str:
    """
    Convierte "/api/storage/chapters/x.pdf" -> "storage/chapters/x.pdf"
    Si ya viene como ruta, regresa normal.
    """
    rel = (file_url or "").replace("\\", "/").strip()
    prefix = "/api/storage/"
    if rel.startswith(prefix):
        rel_storage = rel[len(prefix):]  # "chapters/x.pdf"
        return os.path.join(STORAGE_DIR, rel_storage.replace("/", os.sep))
    return file_url

def _resolve_existing_path(path_or_url: str) -> str:
    p = (path_or_url or "").strip()
    if not p:
        return ""
    p = _physical_from_storage_url(p)
    if not os.path.isabs(p):
        p = os.path.join(os.getcwd(), p)
    return os.path.normpath(p)

def _pick_latest_path(ch: Chapter) -> str:
    corrected = (ch.corrected_file_path or "").strip()
    if corrected:
        return corrected
    return (ch.file_path or "").strip()

def _guess_media_type(path: str) -> str:
    ext = (os.path.splitext(path)[1] or "").lower()
    if ext == ".pdf":
        return "application/pdf"
    if ext == ".doc":
        return "application/msword"
    if ext == ".docx":
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return "application/octet-stream"


# ============================================================
# GET /api/dictaminador/chapters
# ============================================================
@router.get("/chapters", response_model=List[DictChapterOut])
def list_my_chapters(db: Session = Depends(get_db), user=Depends(get_current_user)):
    me = _require_dictaminador(db, user)

    rows = (
        db.query(Chapter, Book)
        .join(Book, Book.id == Chapter.book_id)
        .filter(Chapter.evaluator_id == me.id)
        .order_by(Chapter.deadline_at.asc().nulls_last(), Chapter.updated_at.desc())
        .all()
    )

    out: List[DictChapterOut] = []
    for ch, b in rows:
        days_remaining, is_overdue = _deadline_meta(getattr(ch, "deadline_at", None))

        out.append(DictChapterOut(
            id=int(ch.id),
            title=ch.title,
            status=str(ch.status),
            updated_at=ch.updated_at.isoformat() if ch.updated_at else "",

            book_name=b.name if b else None,
            author_name=ch.author_name,
            author_email=ch.author_email,

            file_path=ch.file_path,
            corrected_file_path=ch.corrected_file_path,
            corrected_updated_at=ch.corrected_updated_at.isoformat() if ch.corrected_updated_at else None,

            deadline_at=ch.deadline_at.isoformat() if ch.deadline_at else None,
            deadline_stage=ch.deadline_stage,
            days_remaining=days_remaining,
            is_overdue=is_overdue,

            author_deadline_at=ch.author_deadline_at.isoformat() if ch.author_deadline_at else None,
            author_deadline_set_at=ch.author_deadline_set_at.isoformat() if ch.author_deadline_set_at else None,
            author_deadline_set_by=int(ch.author_deadline_set_by) if ch.author_deadline_set_by else None,
        ))

    return out


# ============================================================
# PATCH /api/dictaminador/chapters/{id}/status
# ============================================================
@router.patch("/chapters/{chapter_id}/status")
def update_chapter_status(
    chapter_id: int,
    payload: StatusUpdateIn,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    me = _require_dictaminador(db, user)

    ch = (
        db.query(Chapter)
        .filter(Chapter.id == chapter_id, Chapter.evaluator_id == me.id)
        .first()
    )
    if not ch:
        raise HTTPException(status_code=404, detail="Capítulo no encontrado o no asignado a ti")

    new_status = (payload.status or "").strip().upper()
    ch.status = new_status
    ch.updated_at = datetime.utcnow()

    # (Opcional) historial
    if payload.comment and hasattr(ch, "history"):
        from app.models.chapter_history import ChapterHistory
        db.add(ChapterHistory(
            chapter_id=int(ch.id),
            by=getattr(me, "name", "dictaminador"),
            action=f"Cambio de estado a {new_status}",
            detail=payload.comment,
            at=datetime.utcnow()
        ))

    db.add(ch)
    db.commit()
    db.refresh(ch)
    return {"ok": True, "status": str(ch.status)}


# ============================================================
# POST /api/dictaminador/chapters/{id}/author-deadline
# ============================================================
@router.post("/chapters/{chapter_id}/author-deadline")
def set_author_deadline(
    chapter_id: int,
    payload: AuthorDeadlineIn,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    me = _require_dictaminador(db, user)

    ch = (
        db.query(Chapter)
        .filter(Chapter.id == chapter_id, Chapter.evaluator_id == me.id)
        .first()
    )
    if not ch:
        raise HTTPException(status_code=404, detail="Capítulo no encontrado o no asignado a ti")

    # Solo permitir cuando está en correcciones
    if str(ch.status).upper() not in ("CORRECCIONES", "CORRECCIONES_SOLICITADAS_A_AUTOR"):
        raise HTTPException(
            status_code=400,
            detail="Solo puedes fijar fecha límite al autor cuando el capítulo esté en correcciones",
        )

    try:
        deadline_date = datetime.strptime(payload.author_deadline_at, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato de fecha inválido. Use YYYY-MM-DD")

    ch.author_deadline_at = deadline_date
    ch.author_deadline_set_at = datetime.utcnow()
    ch.author_deadline_set_by = int(me.id)
    ch.updated_at = datetime.utcnow()

    db.add(ChapterDeadline(
        chapter_id=int(ch.id),
        stage="AUTOR_CORRECCIONES",
        due_at=deadline_date,
        set_by=int(me.id),
        note=payload.note,
    ))

    db.add(ch)
    db.commit()
    db.refresh(ch)

    return {
        "ok": True,
        "chapter_id": int(ch.id),
        "author_deadline_at": ch.author_deadline_at.isoformat() if ch.author_deadline_at else None,
    }


# ============================================================
# GET /api/dictaminador/chapters/{id}/view-latest
# ============================================================
@router.get("/chapters/{chapter_id}/view-latest")
def view_latest_file(
    chapter_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    me = _require_dictaminador(db, user)

    ch = (
        db.query(Chapter)
        .filter(Chapter.id == chapter_id, Chapter.evaluator_id == me.id)
        .first()
    )
    if not ch:
        raise HTTPException(status_code=404, detail="Capítulo no encontrado o no asignado a ti")

    latest = _pick_latest_path(ch)
    if not latest:
        raise HTTPException(status_code=404, detail="No hay archivo disponible")

    physical = _resolve_existing_path(latest)
    if not physical or not os.path.exists(physical):
        raise HTTPException(status_code=404, detail=f"Archivo no encontrado en servidor: {latest}")

    media_type = _guess_media_type(physical)
    return FileResponse(
        path=physical,
        media_type=media_type,
        headers={"Content-Disposition": f'inline; filename="{os.path.basename(physical)}"'},
    )


# ============================================================
# GET /api/dictaminador/chapters/{id}/download-latest
# ============================================================
@router.get("/chapters/{chapter_id}/download-latest")
def download_latest_file(
    chapter_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    me = _require_dictaminador(db, user)

    ch = (
        db.query(Chapter)
        .filter(Chapter.id == chapter_id, Chapter.evaluator_id == me.id)
        .first()
    )
    if not ch:
        raise HTTPException(status_code=404, detail="Capítulo no encontrado o no asignado a ti")

    latest = _pick_latest_path(ch)
    if not latest:
        raise HTTPException(status_code=404, detail="No hay archivo disponible")

    physical = _resolve_existing_path(latest)
    if not physical or not os.path.exists(physical):
        raise HTTPException(status_code=404, detail=f"Archivo no encontrado en servidor: {latest}")

    media_type = _guess_media_type(physical)
    return FileResponse(
        path=physical,
        media_type=media_type,
        filename=os.path.basename(physical),
        headers={"Content-Disposition": f'attachment; filename="{os.path.basename(physical)}"'},
    )