from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.session import get_db
from app.core.deps import get_current_user

from app.models.user import User
from app.models.book import Book
from app.models.chapter import Chapter
from app.schemas.admin_chapters import AdminChapterRowOut, ChapterStatusUpdateIn


from app.schemas.admin_chapters import (
    AdminChapterRowOut,
    ChapterStatusUpdateIn,
    CorreccionIn,
)

router = APIRouter(prefix="/admin", tags=["admin-chapters"])


# ✅ SOLO ESTO AGREGAS (para que ya exista AssignEvaluatorIn cuando lo uses)
from pydantic import BaseModel
from datetime import datetime
from app.models.dictamen import Dictamen  # ✅ ya tienes el model


class AssignEvaluatorIn(BaseModel):
    evaluator_email: str


def _make_dictamen_folio():
    now = datetime.now()
    return f"DIC-{now.year}-{now.month:02d}-{int(now.timestamp()) % 100000:05d}"

# =========================
# Helpers (mismo estilo)
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


def _require_editorial(db: Session, user_or_payload) -> User:
    uid = _user_id(db, user_or_payload)
    me = db.query(User).filter(User.id == uid).first()
    if not me:
        raise HTTPException(status_code=401, detail="Usuario no encontrado")
    if me.role != "editorial":
        raise HTTPException(status_code=403, detail="No autorizado (solo editorial)")
    return me


# =========================
# GET /admin/chapters
# =========================
@router.get("/chapters", response_model=list[AdminChapterRowOut])
def list_chapters(db: Session = Depends(get_db), user=Depends(get_current_user)):
    _require_editorial(db, user)

    rows = (
        db.query(
            Chapter.id,
            Chapter.title,
            Chapter.status,
            Chapter.updated_at,
            Chapter.book_id,
            Book.name.label("book_name"),
            Chapter.author_name,
            Chapter.author_email,
            Chapter.evaluator_email,
            # folio opcional (si no existe columna, quítalo)
            # Chapter.folio
        )
        .join(Book, Book.id == Chapter.book_id)
        .order_by(Chapter.updated_at.desc(), Chapter.id.desc())
        .all()
    )

    out: list[AdminChapterRowOut] = []
    for r in rows:
        out.append(
            AdminChapterRowOut(
                id=int(r.id),
                folio=None,  # si tienes columna folio en Chapter, aquí la llenas
                title=r.title,
                book_id=int(r.book_id),
                book_name=r.book_name,
                author_name=r.author_name,
                author_email=r.author_email,
                status=r.status,
                updated_at=str(r.updated_at),
                evaluator_email=r.evaluator_email,
            )
        )
    return out


# =========================
# PATCH /admin/chapters/{id}/status
# =========================
@router.patch("/chapters/{chapter_id}/status", response_model=AdminChapterRowOut)
def update_status(
    chapter_id: int,
    payload: ChapterStatusUpdateIn,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    _require_editorial(db, user)

    c = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Capítulo no encontrado")

    c.status = payload.status
    c.updated_at = func.now()

    db.add(c)
    db.commit()
    db.refresh(c)

    b = db.query(Book).filter(Book.id == c.book_id).first()

    return AdminChapterRowOut(
        id=int(c.id),
        folio=None,
        title=c.title,
        book_id=int(c.book_id),
        book_name=b.name if b else "",
        author_name=c.author_name,
        author_email=c.author_email,
        status=c.status,
        updated_at=str(c.updated_at),
        evaluator_email=c.evaluator_email,
    )


# =========================
# POST /admin/chapters/{id}/correccion
# (si quieres guardar comentario de corrección en algún lado)
# =========================
@router.post("/chapters/{chapter_id}/correccion")
def add_correccion(
    chapter_id: int,
    payload: CorreccionIn,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    _require_editorial(db, user)

    c = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Capítulo no encontrado")

    # Aquí depende de tu modelo:
    # - si tienes columna "correccion_comment" o algo así, guárdalo.
    # - si no existe, solo cambiamos status.
    c.status = "CORRECCIONES_SOLICITADAS_A_AUTOR"
    c.updated_at = func.now()

    db.add(c)
    db.commit()

    return {"ok": True}



# =========================
# POST /admin/chapters/{id}/assign
# Asignar dictaminador por correo (debe existir en users y role=dictaminador)
# =========================
@router.post("/chapters/{chapter_id}/assign", response_model=AdminChapterRowOut)
def assign_evaluator(
    chapter_id: int,
    payload: AssignEvaluatorIn,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    _require_editorial(db, user)

    email = (payload.evaluator_email or "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="Escribe el correo del dictaminador.")

    # 1) buscar dictaminador en users
    evaluator = (
        db.query(User)
        .filter(
            User.email == email,
            User.role == "dictaminador",
            User.active == 1,
        )
        .first()
    )
    if not evaluator:
        raise HTTPException(
            status_code=400,
            detail="No existe un dictaminador activo con ese correo.",
        )

    # 2) buscar capítulo
    c = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Capítulo no encontrado")

    # 3) asignar (usa tus columnas reales)
    c.evaluator_id = int(evaluator.id)
    c.evaluator_name = evaluator.name
    c.evaluator_email = evaluator.email

    # 4) actualizar status + fecha
    c.status = "ASIGNADO_A_DICTAMINADOR"
    c.updated_at = func.now()

    db.add(c)
    db.commit()
    db.refresh(c)

    # 5) book_name para respuesta (como ya haces en update_status)
    b = db.query(Book).filter(Book.id == c.book_id).first()

    return AdminChapterRowOut(
        id=int(c.id),
        folio=None,  # (tú aún no tienes columna folio)
        title=c.title,
        book_id=int(c.book_id),
        book_name=b.name if b else "",
        author_name=c.author_name,
        author_email=c.author_email,
        status=c.status,
        updated_at=str(c.updated_at),
        evaluator_email=c.evaluator_email,
    )
