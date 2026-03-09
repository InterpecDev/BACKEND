from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.deps import get_current_user

from app.models.user import User
from app.models.book import Book
from app.models.chapter import Chapter
from app.models.chapter_deadline import ChapterDeadline
from app.models.dictamen import Dictamen
from app.models.dictamen_criterio import DictamenCriterio
from app.models.chapter_history import ChapterHistory

from app.schemas.admin_chapters import (
    AdminChapterRowOut,
    ChapterStatusUpdateIn,
    CorreccionIn,
    AdminChapterFolioUpdateIn,
    EvaluacionUpsertIn,
)

router = APIRouter(prefix="/admin", tags=["admin-chapters"])


class AssignEvaluatorIn(BaseModel):
    evaluator_email: str
    deadline_at: Optional[str] = None  # YYYY-MM-DD


class AssignEvaluatorWithDeadlineIn(BaseModel):
    evaluator_email: str
    deadline_at: str
    deadline_stage: Optional[str] = "DICTAMEN"


class DeadlineUpdateIn(BaseModel):
    deadline_at: str
    deadline_stage: Optional[str] = "DICTAMEN"
    note: Optional[str] = None


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


def _make_dictamen_folio():
    now = datetime.now()
    return f"DIC-{now.year}-{now.month:02d}-{int(now.timestamp()) % 100000:05d}"


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
                deadline_at=str(r.deadline_at) if r.deadline_at else None,
                deadline_stage=r.deadline_stage,
            )
        )
    return out


@router.get("/chapters/{chapter_id}")
def get_chapter_detail(
    chapter_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    _require_editorial(db, user)

    c = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Capítulo no encontrado")

    b = db.query(Book).filter(Book.id == c.book_id).first()

    latest_dictamen = (
        db.query(Dictamen)
        .filter(Dictamen.chapter_id == c.id)
        .order_by(Dictamen.id.desc())
        .first()
    )

    evaluacion_actual = None
    if latest_dictamen:
        criterios = (
            db.query(DictamenCriterio)
            .filter(DictamenCriterio.dictamen_id == latest_dictamen.id)
            .order_by(DictamenCriterio.id.asc())
            .all()
        )

        evaluacion_actual = {
            "tipo": latest_dictamen.tipo,
            "criterios": [
                {
                    "id": f"c{i+1}",
                    "nombre": item.criterio,
                    "puntaje": int(item.value),
                }
                for i, item in enumerate(criterios)
            ],
            "promedio": float(latest_dictamen.promedio) if latest_dictamen.promedio is not None else None,
            "decision": latest_dictamen.decision,
            "comentarios": latest_dictamen.comentarios,
            "conflictos_interes": latest_dictamen.conflicto_interes,
        }

    versions = []
    for v in c.versions:
        versions.append({
            "id": str(v.id),
            "version_label": v.version_label,
            "file_name": v.file_name,
            "uploaded_at": str(v.uploaded_at),
            "note": v.note,
            "uploaded_by": getattr(v, "uploaded_by", "autor"),
        })

    history = []
    for h in c.history:
        history.append({
            "id": str(h.id),
            "at": str(h.at),
            "by": h.by,
            "action": h.action,
            "detail": h.detail,
        })

    return {
        "id": c.id,
        "folio": c.folio,
        "title": c.title,
        "book": {
            "id": b.id if b else None,
            "name": b.name if b else "",
        },
        "author_name": c.author_name,
        "author_email": c.author_email,
        "status": c.status,
        "evaluator_name": c.evaluator_name,
        "evaluator_email": c.evaluator_email,
        "deadline_at": str(c.deadline_at) if c.deadline_at else None,
        "deadline_stage": c.deadline_stage,
        "versions": versions,
        "history": history,
        "evaluacion_actual": evaluacion_actual,
    }


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
        deadline_at=str(c.deadline_at) if c.deadline_at else None,
        deadline_stage=c.deadline_stage,
    )


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

    c = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Capítulo no encontrado")

    c.evaluator_id = int(evaluator.id)
    c.evaluator_name = evaluator.name
    c.evaluator_email = evaluator.email

    c.status = "ASIGNADO_A_DICTAMINADOR"
    c.updated_at = func.now()

    if payload.deadline_at:
        try:
            deadline_date = datetime.strptime(payload.deadline_at, "%Y-%m-%d")
            c.deadline_at = deadline_date
            c.deadline_stage = "DICTAMEN"
            c.deadline_set_at = datetime.now()
            c.deadline_set_by = _user_id(db, user)

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

    c = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Capítulo no encontrado")

    c.evaluator_id = int(evaluator.id)
    c.evaluator_name = evaluator.name
    c.evaluator_email = evaluator.email

    c.status = "ASIGNADO_A_DICTAMINADOR"
    c.updated_at = func.now()

    try:
        deadline_date = datetime.strptime(payload.deadline_at, "%Y-%m-%d")
        c.deadline_at = deadline_date
        c.deadline_stage = payload.deadline_stage or "DICTAMEN"
        c.deadline_set_at = datetime.now()
        c.deadline_set_by = _user_id(db, user)

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

        old_deadline = str(c.deadline_at) if c.deadline_at else "ninguna"

        c.deadline_at = deadline_date
        c.deadline_stage = payload.deadline_stage
        c.deadline_set_at = datetime.now()
        c.deadline_set_by = _user_id(db, user)
        c.updated_at = func.now()

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


@router.post("/chapters/{chapter_id}/evaluacion/upsert")
def upsert_evaluacion(
    chapter_id: int,
    payload: EvaluacionUpsertIn,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    me = _require_editorial(db, user)

    c = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="Capítulo no encontrado")

    if int(payload.chapter_id) != int(chapter_id):
        raise HTTPException(status_code=400, detail="chapter_id no coincide con la URL")

    if not c.evaluator_id:
        raise HTTPException(
            status_code=400,
            detail="El capítulo no tiene dictaminador asignado. Asigna uno antes de guardar la evaluación."
        )

    if not payload.criterios:
        raise HTTPException(status_code=400, detail="Debes enviar al menos un criterio.")

    promedio_real = round(
        sum(int(item.puntaje) for item in payload.criterios) / len(payload.criterios),
        1
    )

    d = (
        db.query(Dictamen)
        .filter(
            Dictamen.chapter_id == c.id,
            Dictamen.evaluador_id == c.evaluator_id,
        )
        .first()
    )

    if not d:
        d = Dictamen(
            folio=_make_dictamen_folio(),
            chapter_id=c.id,
            evaluador_id=c.evaluator_id,
            tipo=payload.tipo.strip()[:80],
            decision=payload.decision,
            status="BORRADOR",
            promedio=promedio_real,
            comentarios=payload.comentarios,
            conflicto_interes=payload.conflictos_interes,
            recipient_name=c.author_name,
        )
        db.add(d)
        db.flush()
    else:
        d.tipo = payload.tipo.strip()[:80]
        d.decision = payload.decision
        d.promedio = promedio_real
        d.comentarios = payload.comentarios
        d.conflicto_interes = payload.conflictos_interes
        d.updated_at = datetime.now()

        db.query(DictamenCriterio).filter(DictamenCriterio.dictamen_id == d.id).delete()

    for item in payload.criterios:
        db.add(
            DictamenCriterio(
                dictamen_id=d.id,
                criterio=item.nombre.strip(),
                value=int(item.puntaje),
            )
        )

    if payload.decision == "APROBADO":
        c.status = "APROBADO"
    elif payload.decision == "RECHAZADO":
        c.status = "RECHAZADO"
    elif payload.decision == "CORRECCIONES":
        c.status = "CORRECCIONES_SOLICITADAS_A_AUTOR"

    c.updated_at = func.now()

    db.add(
        ChapterHistory(
            chapter_id=c.id,
            by=me.name,
            action="Evaluación guardada",
            detail=f"Evaluación {payload.decision} guardada con promedio {promedio_real}",
        )
    )

    db.add(c)
    db.commit()
    db.refresh(d)

    return {
        "ok": True,
        "dictamen_id": int(d.id),
        "folio": d.folio,
        "promedio": float(d.promedio) if d.promedio is not None else None,
        "decision": d.decision,
        "status_capitulo": c.status,
    }


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
        deadline_at=str(c.deadline_at) if c.deadline_at else None,
        deadline_stage=c.deadline_stage,
    )