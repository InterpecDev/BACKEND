from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from app.db.session import get_db
from app.core.deps import get_current_user

from app.models.user import User
from app.models.book import Book
from app.models.chapter import Chapter
from app.models.chapter_version import ChapterVersion
from app.models.dictamen import Dictamen
from app.models.chapter_history import ChapterHistory
from app.models.chapter_deadline import ChapterDeadline
from app.schemas.admin_chapters import AdminChapterRowOut, ChapterStatusUpdateIn
from app.schemas.admin_chapters import AdminChapterFolioUpdateIn
from datetime import datetime, time

from app.schemas.admin_chapters import (
    AdminChapterRowOut,
    ChapterStatusUpdateIn,
    CorreccionIn,
)

router = APIRouter(prefix="/admin", tags=["admin-chapters"])


# ✅ Pydantic models para fechas
from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from app.models.dictamen import Dictamen  # ✅ ya tienes el model


class AssignEvaluatorIn(BaseModel):
    evaluator_email: str
    deadline_at: Optional[str] = None  # NUEVO: formato YYYY-MM-DD


class AssignEvaluatorWithDeadlineIn(BaseModel):
    evaluator_email: str
    deadline_at: str  # requerido para asignación con fecha
    deadline_stage: Optional[str] = "DICTAMEN"


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
# GET /admin/chapters (listado)
# =========================
@router.get("/chapters", response_model=list[AdminChapterRowOut])
def list_chapters(db: Session = Depends(get_db), user=Depends(get_current_user)):
    _require_editorial(db, user)

    rows = (
        db.query(
            Chapter.id,
            Chapter.folio, 
            Chapter.title,
            Chapter.status,
            Chapter.updated_at,
            Chapter.book_id,
            Book.name.label("book_name"),
            Chapter.author_name,
            Chapter.author_email,
            Chapter.evaluator_email,
            Chapter.evaluator_name,
            # NUEVO: incluir campos de fechas
            Chapter.deadline_at,
            Chapter.deadline_stage,
            Chapter.deadline_set_at,
            Chapter.deadline_set_by,
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
                folio=r.folio,
                title=r.title,
                book_id=int(r.book_id),
                book_name=r.book_name,
                author_name=r.author_name,
                author_email=r.author_email,
                status=r.status,
                updated_at=str(r.updated_at),
                evaluator_email=r.evaluator_email,
                # NUEVO: incluir fechas en respuesta
                deadline_at=str(r.deadline_at) if r.deadline_at else None,
                deadline_stage=r.deadline_stage,
            )
        )
    return out


# =========================
# GET /admin/chapters/{chapter_id} - DETALLE COMPLETO DEL CAPÍTULO
# =========================
@router.get("/chapters/{chapter_id}")
def get_chapter_detail(
    chapter_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    _require_editorial(db, user)
    
    # Obtener capítulo con todas las relaciones
    c = (
        db.query(Chapter)
        .options(
            joinedload(Chapter.book),
            joinedload(Chapter.versions),
            joinedload(Chapter.dictamenes).joinedload(Dictamen.evaluador),
            joinedload(Chapter.history),
        )
        .filter(Chapter.id == chapter_id)
        .first()
    )
    
    if not c:
        raise HTTPException(status_code=404, detail="Capítulo no encontrado")
    
    # Obtener el libro
    book = c.book
    
    # Versiones
    versions = []
    for v in c.versions or []:
        versions.append({
            "id": v.id,
            "version_label": v.version_label,
            "file_name": v.file_name,
            "file_path": v.file_path,
            "note": v.note,
            "uploaded_at": v.uploaded_at,
            "uploaded_by": "autor"  # Ajustar según corresponda
        })
    
    # Dictámenes históricos
    dictamenes = []
    for d in c.dictamenes or []:
        dictamenes.append({
            "id": d.id,
            "folio": d.folio,
            "evaluator_name": d.evaluador.name if d.evaluador else None,
            "tipo": d.tipo,
            "promedio": d.promedio,
            "decision": d.decision,
            "status": d.status,
            "created_at": d.created_at,
            "firmado": d.status == "FIRMADO"
        })
    
    # Dictamen actual (el más reciente)
    dictamen_actual = None
    if c.dictamenes:
        # Ordenar por fecha de creación para obtener el último
        dictamenes_ordenados = sorted(c.dictamenes, key=lambda x: x.created_at, reverse=True)
        if dictamenes_ordenados:
            d = dictamenes_ordenados[0]
            
            # Obtener criterios del dictamen si existen
            criterios = []
            if hasattr(d, 'criterios') and d.criterios:
                for criterio in d.criterios:
                    criterios.append({
                        "id": criterio.id,
                        "nombre": criterio.criterio,
                        "puntaje": criterio.value
                    })
            
            dictamen_actual = {
                "id": d.id,
                "folio": d.folio,
                "evaluador_id": d.evaluador_id,
                "evaluador_nombre": d.evaluador.name if d.evaluador else None,
                "evaluador_email": d.evaluador.email if d.evaluador else None,
                "tipo": d.tipo,
                "titulo": c.title,
                "criterios": criterios,
                "promedio": d.promedio,
                "decision": d.decision,
                "comentarios": d.comentarios,
                "conflictos_interes": d.conflicto_interes,
                "fecha_evaluacion": d.created_at,
                "fecha_firma": d.signed_at,
                "firmado": d.status == "FIRMADO",
                "archivo_firma": d.signed_pdf_path
            }
    
    # Historial
    history = []
    for h in c.history or []:
        history.append({
            "id": h.id,
            "at": h.at,
            "by": h.by,
            "action": h.action,
            "detail": h.detail
        })
    
    # Evaluación actual (puede ser el mismo dictamen)
    evaluacion_actual = dictamen_actual
    
    # Construir respuesta completa
    return {
        "id": c.id,
        "folio": c.folio,
        "title": c.title,
        "book": {
            "id": book.id if book else None,
            "name": book.name if book else None
        },
        "book_name": book.name if book else None,
        "author_name": c.author_name,
        "author_email": c.author_email,
        "status": c.status,
        "updated_at": c.updated_at,
        "evaluator_name": c.evaluator_name,
        "evaluator_email": c.evaluator_email,
        "deadline_at": c.deadline_at,
        "deadline_stage": c.deadline_stage,
        "versions": versions,
        "dictamenes": dictamenes,
        "dictamen_actual": dictamen_actual,
        "history": history,
        "evaluacion_actual": evaluacion_actual
    }


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
        folio=c.folio,
        title=c.title,
        book_id=int(c.book_id),
        book_name=b.name if b else "",
        author_name=c.author_name,
        author_email=c.author_email,
        status=c.status,
        updated_at=str(c.updated_at),
        evaluator_email=c.evaluator_email,
        # NUEVO: incluir fechas en respuesta
        deadline_at=str(c.deadline_at) if c.deadline_at else None,
        deadline_stage=c.deadline_stage,
    )


# =========================
# POST /admin/chapters/{id}/correccion
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

    c.status = "CORRECCIONES_SOLICITADAS_A_AUTOR"
    c.updated_at = func.now()

    db.add(c)
    db.commit()

    return {"ok": True}


# =========================
# POST /admin/chapters/{id}/assign
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

    # 3) asignar dictaminador
    c.evaluator_id = int(evaluator.id)
    c.evaluator_name = evaluator.name
    c.evaluator_email = evaluator.email

    # 4) actualizar status
    c.status = "ASIGNADO_A_DICTAMINADOR"
    c.updated_at = func.now()

    # 5) NUEVO: guardar fecha límite si se proporcionó
    if payload.deadline_at:
        try:
            # Convertir string a datetime
            deadline_date = datetime.strptime(payload.deadline_at, "%Y-%m-%d")
            c.deadline_at = deadline_date
            c.deadline_stage = "DICTAMEN"  # etapa por defecto
            c.deadline_set_at = datetime.now()
            c.deadline_set_by = _user_id(db, user)

            # Guardar en historial de deadlines
            deadline_record = ChapterDeadline(
                chapter_id=c.id,
                stage="DICTAMEN",
                due_at=deadline_date,
                set_by=_user_id(db, user),
                note="Fecha límite establecida al asignar dictaminador"
            )
            db.add(deadline_record)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Formato de fecha inválido. Use YYYY-MM-DD"
            )

    db.add(c)
    db.commit()
    db.refresh(c)

    # 6) book_name para respuesta
    b = db.query(Book).filter(Book.id == c.book_id).first()

    return AdminChapterRowOut(
        id=int(c.id),
        folio=c.folio,
        title=c.title,
        book_id=int(c.book_id),
        book_name=b.name if b else "",
        author_name=c.author_name,
        author_email=c.author_email,
        status=c.status,
        updated_at=str(c.updated_at),
        evaluator_email=c.evaluator_email,
        # NUEVO: incluir fechas en respuesta
        deadline_at=str(c.deadline_at) if c.deadline_at else None,
        deadline_stage=c.deadline_stage,
    )


# =========================
# POST /admin/chapters/{id}/assign-with-deadline
# =========================
@router.post("/chapters/{chapter_id}/assign-with-deadline", response_model=AdminChapterRowOut)
def assign_evaluator_with_deadline(
    chapter_id: int,
    payload: AssignEvaluatorWithDeadlineIn,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    _require_editorial(db, user)

    email = (payload.evaluator_email or "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="Escribe el correo del dictaminador.")

    if not payload.deadline_at:
        raise HTTPException(status_code=400, detail="La fecha límite es requerida.")

    # 1) buscar dictaminador
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

    # 3) asignar dictaminador
    c.evaluator_id = int(evaluator.id)
    c.evaluator_name = evaluator.name
    c.evaluator_email = evaluator.email

    # 4) actualizar status
    c.status = "ASIGNADO_A_DICTAMINADOR"
    c.updated_at = func.now()

    # 5) guardar fecha límite
    try:
        deadline_date = datetime.strptime(payload.deadline_at, "%Y-%m-%d")
        c.deadline_at = deadline_date
        c.deadline_stage = payload.deadline_stage or "DICTAMEN"
        c.deadline_set_at = datetime.now()
        c.deadline_set_by = _user_id(db, user)

        # Guardar en historial
        deadline_record = ChapterDeadline(
            chapter_id=c.id,
            stage=payload.deadline_stage or "DICTAMEN",
            due_at=deadline_date,
            set_by=_user_id(db, user),
            note="Fecha límite establecida al asignar dictaminador"
        )
        db.add(deadline_record)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Formato de fecha inválido. Use YYYY-MM-DD"
        )

    db.add(c)
    db.commit()
    db.refresh(c)

    b = db.query(Book).filter(Book.id == c.book_id).first()

    return AdminChapterRowOut(
        id=int(c.id),
        folio=c.folio,
        title=c.title,
        book_id=int(c.book_id),
        book_name=b.name if b else "",
        author_name=c.author_name,
        author_email=c.author_email,
        status=c.status,
        updated_at=str(c.updated_at),
        evaluator_email=c.evaluator_email,
        deadline_at=str(c.deadline_at) if c.deadline_at else None,
        deadline_stage=c.deadline_stage,
    )


# =========================
# PATCH /admin/chapters/{id}/deadline
# =========================
class DeadlineUpdateIn(BaseModel):
    deadline_at: str  # YYYY-MM-DD
    deadline_stage: Optional[str] = "DICTAMEN"
    note: Optional[str] = None

@router.patch("/chapters/{chapter_id}/deadline", response_model=AdminChapterRowOut)
def update_deadline(
    chapter_id: int,
    payload: DeadlineUpdateIn,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    _require_editorial(db, user)

    c = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Capítulo no encontrado")

    try:
        deadline_date = datetime.strptime(payload.deadline_at, "%Y-%m-%d")
        
        # Guardar fecha anterior para nota
        old_deadline = str(c.deadline_at) if c.deadline_at else "ninguna"
        
        # Actualizar capítulo
        c.deadline_at = deadline_date
        c.deadline_stage = payload.deadline_stage
        c.deadline_set_at = datetime.now()
        c.deadline_set_by = _user_id(db, user)
        c.updated_at = func.now()

        # Guardar en historial
        note = payload.note or f"Fecha límite actualizada: {old_deadline} → {payload.deadline_at}"
        deadline_record = ChapterDeadline(
            chapter_id=c.id,
            stage=payload.deadline_stage,
            due_at=deadline_date,
            set_by=_user_id(db, user),
            note=note
        )
        db.add(deadline_record)

        db.add(c)
        db.commit()
        db.refresh(c)

    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Formato de fecha inválido. Use YYYY-MM-DD"
        )

    b = db.query(Book).filter(Book.id == c.book_id).first()

    return AdminChapterRowOut(
        id=int(c.id),
        folio=c.folio,
        title=c.title,
        book_id=int(c.book_id),
        book_name=b.name if b else "",
        author_name=c.author_name,
        author_email=c.author_email,
        status=c.status,
        updated_at=str(c.updated_at),
        evaluator_email=c.evaluator_email,
        deadline_at=str(c.deadline_at) if c.deadline_at else None,
        deadline_stage=c.deadline_stage,
    )


# =========================
# GET /admin/chapters/{id}/deadlines - HISTORIAL DE FECHAS LÍMITE
# =========================
class DeadlineHistoryOut(BaseModel):
    id: int
    stage: str
    due_at: str
    set_by_name: Optional[str] = None
    set_by_email: Optional[str] = None
    note: Optional[str] = None
    created_at: str

    class Config:
        from_attributes = True

@router.get("/chapters/{chapter_id}/deadlines", response_model=list[DeadlineHistoryOut])
def get_deadline_history(
    chapter_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    _require_editorial(db, user)

    c = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Capítulo no encontrado")

    deadlines = (
        db.query(ChapterDeadline)
        .filter(ChapterDeadline.chapter_id == chapter_id)
        .order_by(ChapterDeadline.created_at.desc())
        .all()
    )

    result = []
    for d in deadlines:
        setter_name = None
        setter_email = None
        if d.setter:
            setter_name = d.setter.name
            setter_email = d.setter.email

        result.append(DeadlineHistoryOut(
            id=d.id,
            stage=d.stage,
            due_at=str(d.due_at),
            set_by_name=setter_name,
            set_by_email=setter_email,
            note=d.note,
            created_at=str(d.created_at)
        ))

    return result


# =========================
# PATCH /admin/chapters/{id}/folio
# =========================
from sqlalchemy.exc import IntegrityError

@router.patch("/chapters/{chapter_id}/folio", response_model=AdminChapterRowOut)
def update_chapter_folio(
    chapter_id: int,
    payload: AdminChapterFolioUpdateIn,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    _require_editorial(db, user)

    folio = (payload.folio or "").strip()
    if not folio:
        raise HTTPException(status_code=400, detail="El folio no puede ir vacío.")

    c = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Capítulo no encontrado")

    c.folio = folio
    c.updated_at = func.now()

    try:
        db.add(c)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Ese folio ya está en uso por otro capítulo.")

    db.refresh(c)
    b = db.query(Book).filter(Book.id == c.book_id).first()

    return AdminChapterRowOut(
        id=int(c.id),
        folio=c.folio,
        title=c.title,
        book_id=int(c.book_id),
        book_name=b.name if b else "",
        author_name=c.author_name,
        author_email=c.author_email,
        status=c.status,
        updated_at=str(c.updated_at),
        evaluator_email=getattr(c, "evaluator_email", None),
        # NUEVO: incluir fechas en respuesta
        deadline_at=str(c.deadline_at) if c.deadline_at else None,
        deadline_stage=c.deadline_stage,
    )