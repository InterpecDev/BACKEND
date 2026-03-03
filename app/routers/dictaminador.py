# app/routers/dictaminador.py
import os
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.chapter import Chapter
from app.models.book import Book
from app.models.chapter_history import ChapterHistory

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

    # editorial -> dictaminador
    deadline_at: Optional[str] = None
    deadline_stage: Optional[str] = None

    # dictaminador -> autor  ✅ NUEVO
    author_deadline_at: Optional[str] = None

    class Config:
        from_attributes = True


class StatusUpdateIn(BaseModel):
    status: str
    comment: Optional[str] = None

    # dictaminador -> autor ✅ NUEVO (si viene, se guarda)
    author_deadline_at: Optional[str] = None  # ejemplo: "2026-03-10T23:59:59"


# =========================
# Helpers auth (tu mismo estilo)
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


# =========================
# Helpers archivos (Railway)
# =========================
def _guess_media_type(ext: str) -> str:
    ext = (ext or "").lower()
    if ext == ".pdf":
        return "application/pdf"
    if ext == ".doc":
        return "application/msword"
    if ext == ".docx":
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return "application/octet-stream"


def _pick_latest_file_path(ch: Chapter) -> str:
    corrected = (getattr(ch, "corrected_file_path", None) or "").strip()
    if corrected:
        return corrected
    return (getattr(ch, "file_path", "") or "").strip()


def _resolve_physical_path(path_from_db: str) -> str:
    """
    Si guardas rutas tipo:
      - "storage/chapters/x.docx"
      - "/app/storage/chapters/x.docx"
    las resolvemos a una ruta real del contenedor.
    """
    p = (path_from_db or "").replace("\\", "/").strip()
    if not p:
        return ""

    # si ya es absoluta, la dejamos
    if os.path.isabs(p):
        return p

    # si es relativa, la hacemos relativa al cwd
    return os.path.join(os.getcwd(), p)


# =========================
# GET /dictaminador/chapters
# =========================
@router.get("/chapters", response_model=List[DictaminadorChapterOut])
def list_my_chapters(db: Session = Depends(get_db), user=Depends(get_current_user)):
    me = _require_dictaminador(db, user)

    rows = (
        db.query(Chapter, Book)
        .join(Book, Book.id == Chapter.book_id)
        .filter(Chapter.evaluator_id == me.id)
        .order_by(Chapter.updated_at.desc(), Chapter.id.desc())
        .all()
    )

    out: List[DictaminadorChapterOut] = []
    for ch, b in rows:
        out.append(
            DictaminadorChapterOut(
                id=int(ch.id),
                title=ch.title,
                status=str(ch.status),
                updated_at=ch.updated_at.isoformat() if ch.updated_at else "",

                file_path=getattr(ch, "file_path", None),
                book_name=b.name if b else None,
                author_name=getattr(ch, "author_name", None),
                author_email=getattr(ch, "author_email", None),

                deadline_at=ch.deadline_at.isoformat() if getattr(ch, "deadline_at", None) else None,
                deadline_stage=getattr(ch, "deadline_stage", None),

                # ✅ NUEVO
                author_deadline_at=ch.author_deadline_at.isoformat() if getattr(ch, "author_deadline_at", None) else None,
            )
        )

    return out


# =========================
# PATCH /dictaminador/chapters/{id}/status
# =========================
@router.patch("/chapters/{chapter_id}/status", response_model=DictaminadorChapterOut)
def update_status(
    chapter_id: int,
    payload: StatusUpdateIn,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    me = _require_dictaminador(db, user)

    new_status = (payload.status or "").strip().upper()
    if new_status not in (
        "EN_REVISION",
        "CORRECCIONES",
        "APROBADO",
        "RECHAZADO",
        "EN_REVISION_DICTAMINADOR",
        "CORRECCIONES_SOLICITADAS_A_AUTOR",
        "REENVIADO_POR_AUTOR",
        "REVISADO_POR_EDITORIAL",
        "LISTO_PARA_FIRMA",
        "FIRMADO",
        "ASIGNADO_A_DICTAMINADOR",
        "ENVIADO_A_DICTAMINADOR",
        "RECIBIDO",
    ):
        raise HTTPException(status_code=400, detail="Estado inválido")

    ch = (
        db.query(Chapter)
        .filter(Chapter.id == chapter_id, Chapter.evaluator_id == me.id)
        .first()
    )
    if not ch:
        raise HTTPException(status_code=404, detail="Capítulo no encontrado o no asignado a ti")

    # comentario obligatorio para correcciones / rechazo (como tú lo manejas en UI)
    comment = (payload.comment or "").strip()
    if new_status in ("CORRECCIONES", "RECHAZADO") and not comment:
        raise HTTPException(status_code=400, detail="Escribe el comentario")

    # ✅ actualiza status
    ch.status = new_status
    ch.updated_at = datetime.utcnow()

    # ✅ NUEVO: si el dictaminador manda author_deadline_at, guardarlo
    if payload.author_deadline_at:
        try:
            # acepta "YYYY-MM-DDTHH:MM:SS" (lo que mandas desde frontend)
            ch.author_deadline_at = datetime.fromisoformat(payload.author_deadline_at.replace("Z", ""))
            ch.author_deadline_set_at = datetime.utcnow()
            ch.author_deadline_set_by = int(me.id)
        except Exception:
            raise HTTPException(status_code=400, detail="author_deadline_at inválido (usa ISO, ej: 2026-03-10T23:59:59)")

    # guardar historial (opcional pero recomendado)
    if comment:
        db.add(
            ChapterHistory(
                chapter_id=int(ch.id),
                by=me.name,
                action=f"DICTAMINADOR_STATUS_{new_status}",
                detail=comment,
                at=datetime.utcnow(),
            )
        )

    db.add(ch)
    db.commit()
    db.refresh(ch)

    b = db.query(Book).filter(Book.id == ch.book_id).first()

    return DictaminadorChapterOut(
        id=int(ch.id),
        title=ch.title,
        status=str(ch.status),
        updated_at=ch.updated_at.isoformat() if ch.updated_at else "",

        file_path=getattr(ch, "file_path", None),
        book_name=b.name if b else None,
        author_name=getattr(ch, "author_name", None),
        author_email=getattr(ch, "author_email", None),

        deadline_at=ch.deadline_at.isoformat() if getattr(ch, "deadline_at", None) else None,
        deadline_stage=getattr(ch, "deadline_stage", None),

        # ✅ NUEVO
        author_deadline_at=ch.author_deadline_at.isoformat() if getattr(ch, "author_deadline_at", None) else None,
    )


# =========================
# GET /dictaminador/chapters/{id}/view-latest
# =========================
@router.get("/chapters/{chapter_id}/view-latest")
def view_latest(chapter_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    me = _require_dictaminador(db, user)

    ch = (
        db.query(Chapter)
        .filter(Chapter.id == chapter_id, Chapter.evaluator_id == me.id)
        .first()
    )
    if not ch:
        raise HTTPException(status_code=404, detail="Capítulo no encontrado o no asignado a ti")

    latest = _pick_latest_file_path(ch)
    if not latest:
        raise HTTPException(status_code=404, detail="Este capítulo no tiene archivo")

    physical = _resolve_physical_path(latest)
    if not physical or not os.path.exists(physical):
        raise HTTPException(status_code=404, detail="Archivo no encontrado en el servidor")

    ext = os.path.splitext(physical)[1] or ".bin"
    return FileResponse(
        path=physical,
        media_type=_guess_media_type(ext),
        headers={"Content-Disposition": f'inline; filename="{os.path.basename(physical)}"'},
    )


# =========================
# GET /dictaminador/chapters/{id}/download-latest
# =========================
@router.get("/chapters/{chapter_id}/download-latest")
def download_latest(chapter_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    me = _require_dictaminador(db, user)

    ch = (
        db.query(Chapter)
        .filter(Chapter.id == chapter_id, Chapter.evaluator_id == me.id)
        .first()
    )
    if not ch:
        raise HTTPException(status_code=404, detail="Capítulo no encontrado o no asignado a ti")

    latest = _pick_latest_file_path(ch)
    if not latest:
        raise HTTPException(status_code=404, detail="Este capítulo no tiene archivo")

    physical = _resolve_physical_path(latest)
    if not physical or not os.path.exists(physical):
        raise HTTPException(status_code=404, detail="Archivo no encontrado en el servidor")

    ext = os.path.splitext(physical)[1] or ".bin"
    return FileResponse(
        path=physical,
        media_type=_guess_media_type(ext),
        filename=os.path.basename(physical),
        headers={"Content-Disposition": f'attachment; filename="{os.path.basename(physical)}"'},
    )