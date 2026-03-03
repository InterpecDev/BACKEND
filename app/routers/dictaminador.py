from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, date
from typing import List, Optional
from pydantic import BaseModel

from app.db.session import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.chapter import Chapter
from app.models.book import Book

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
    
    # ✅ NUEVO: campos de fecha límite
    deadline_at: Optional[str] = None
    deadline_stage: Optional[str] = None
    days_remaining: Optional[int] = None
    is_overdue: Optional[bool] = False
    
    class Config:
        from_attributes = True

class StatusUpdateIn(BaseModel):
    status: str
    comment: Optional[str] = None

# =========================
# Helpers (mismo estilo que admin_chapters.py)
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
# GET /dictaminador/chapters
# =========================
@router.get("/chapters", response_model=List[DictaminadorChapterOut])
def list_my_chapters(
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """Obtiene los capítulos asignados al dictaminador actual"""
    
    dictaminador = _require_dictaminador(db, user)
    
    chapters = (
        db.query(
            Chapter.id,
            Chapter.title,
            Chapter.status,
            Chapter.updated_at,
            Chapter.file_path,
            Chapter.book_id,
            Book.name.label("book_name"),
            Chapter.author_name,
            Chapter.author_email,
            Chapter.deadline_at,
            Chapter.deadline_stage,
        )
        .join(Book, Book.id == Chapter.book_id)
        .filter(Chapter.evaluator_id == dictaminador.id)
        .order_by(
            Chapter.deadline_at.asc().nulls_last(),
            Chapter.updated_at.desc()
        )
        .all()
    )
    
    result = []
    today = date.today()
    
    for c in chapters:
        days_remaining = None
        is_overdue = False
        
        if c.deadline_at:
            if isinstance(c.deadline_at, datetime):
                deadline_date = c.deadline_at.date()
            else:
                deadline_date = c.deadline_at
            days_remaining = (deadline_date - today).days
            is_overdue = days_remaining < 0
        
        result.append(DictaminadorChapterOut(
            id=c.id,
            title=c.title,
            status=c.status,
            updated_at=str(c.updated_at),
            file_path=c.file_path,
            book_name=c.book_name,
            author_name=c.author_name,
            author_email=c.author_email,
            deadline_at=str(c.deadline_at) if c.deadline_at else None,
            deadline_stage=c.deadline_stage,
            days_remaining=days_remaining,
            is_overdue=is_overdue
        ))
    
    return result

# =========================
# GET /dictaminador/chapters/{chapter_id}
# =========================
@router.get("/chapters/{chapter_id}", response_model=DictaminadorChapterOut)
def get_chapter_detail(
    chapter_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """Obtiene detalle de un capítulo específico"""
    
    dictaminador = _require_dictaminador(db, user)
    
    c = (
        db.query(
            Chapter.id,
            Chapter.title,
            Chapter.status,
            Chapter.updated_at,
            Chapter.file_path,
            Chapter.book_id,
            Book.name.label("book_name"),
            Chapter.author_name,
            Chapter.author_email,
            Chapter.deadline_at,
            Chapter.deadline_stage,
        )
        .join(Book, Book.id == Chapter.book_id)
        .filter(
            Chapter.id == chapter_id,
            Chapter.evaluator_id == dictaminador.id
        )
        .first()
    )
    
    if not c:
        raise HTTPException(status_code=404, detail="Capítulo no encontrado o no asignado a ti")
    
    today = date.today()
    days_remaining = None
    is_overdue = False
    
    if c.deadline_at:
        if isinstance(c.deadline_at, datetime):
            deadline_date = c.deadline_at.date()
        else:
            deadline_date = c.deadline_at
        days_remaining = (deadline_date - today).days
        is_overdue = days_remaining < 0
    
    return DictaminadorChapterOut(
        id=c.id,
        title=c.title,
        status=c.status,
        updated_at=str(c.updated_at),
        file_path=c.file_path,
        book_name=c.book_name,
        author_name=c.author_name,
        author_email=c.author_email,
        deadline_at=str(c.deadline_at) if c.deadline_at else None,
        deadline_stage=c.deadline_stage,
        days_remaining=days_remaining,
        is_overdue=is_overdue
    )

# =========================
# GET /dictaminador/chapters/{chapter_id}/view-latest
# =========================
@router.get("/chapters/{chapter_id}/view-latest")
def view_latest_file(
    chapter_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """Ver el último archivo del capítulo en el navegador"""
    dictaminador = _require_dictaminador(db, user)
    
    chapter = db.query(Chapter).filter(
        Chapter.id == chapter_id,
        Chapter.evaluator_id == dictaminador.id
    ).first()
    
    if not chapter:
        raise HTTPException(status_code=404, detail="Capítulo no encontrado")
    
    # Determinar qué archivo mostrar (el más reciente)
    file_path = chapter.corrected_file_path or chapter.file_path
    
    if not file_path:
        raise HTTPException(status_code=404, detail="No hay archivo disponible")
    
    from fastapi.responses import FileResponse
    import os
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Archivo no encontrado en el servidor")
    
    return FileResponse(
        file_path,
        media_type="application/octet-stream",
        filename=os.path.basename(file_path)
    )

# =========================
# GET /dictaminador/chapters/{chapter_id}/download-latest
# =========================
@router.get("/chapters/{chapter_id}/download-latest")
def download_latest_file(
    chapter_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """Descargar el último archivo del capítulo"""
    dictaminador = _require_dictaminador(db, user)
    
    chapter = db.query(Chapter).filter(
        Chapter.id == chapter_id,
        Chapter.evaluator_id == dictaminador.id
    ).first()
    
    if not chapter:
        raise HTTPException(status_code=404, detail="Capítulo no encontrado")
    
    file_path = chapter.corrected_file_path or chapter.file_path
    
    if not file_path:
        raise HTTPException(status_code=404, detail="No hay archivo disponible")
    
    from fastapi.responses import FileResponse
    import os
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Archivo no encontrado en el servidor")
    
    return FileResponse(
        file_path,
        media_type="application/octet-stream",
        filename=os.path.basename(file_path),
        headers={"Content-Disposition": f"attachment; filename={os.path.basename(file_path)}"}
    )

# =========================
# PATCH /dictaminador/chapters/{chapter_id}/status
# =========================
@router.patch("/chapters/{chapter_id}/status")
def update_chapter_status(
    chapter_id: int,
    payload: StatusUpdateIn,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """Actualizar estado de un capítulo"""
    dictaminador = _require_dictaminador(db, user)
    
    chapter = db.query(Chapter).filter(
        Chapter.id == chapter_id,
        Chapter.evaluator_id == dictaminador.id
    ).first()
    
    if not chapter:
        raise HTTPException(status_code=404, detail="Capítulo no encontrado")
    
    chapter.status = payload.status
    chapter.updated_at = datetime.now()
    
    # Si hay comentario, podrías guardarlo en un historial
    if payload.comment and hasattr(chapter, 'history'):
        from app.models.chapter_history import ChapterHistory
        history = ChapterHistory(
            chapter_id=chapter.id,
            by=dictaminador.name,
            action=f"Cambio de estado a {payload.status}",
            detail=payload.comment,
            at=datetime.now()
        )
        db.add(history)
    
    db.commit()
    db.refresh(chapter)
    
    return {"ok": True, "status": chapter.status}from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, date
from typing import List, Optional
from pydantic import BaseModel

from app.db.session import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.chapter import Chapter
from app.models.book import Book

# ✅ NUEVO (historial deadlines)
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

    # ✅ EXISTENTE: fecha límite Editorial -> Dictaminador
    deadline_at: Optional[str] = None
    deadline_stage: Optional[str] = None
    days_remaining: Optional[int] = None
    is_overdue: Optional[bool] = False

    # ✅ NUEVO: fecha límite Dictaminador -> Autor (correcciones)
    author_deadline_at: Optional[str] = None
    author_deadline_set_at: Optional[str] = None
    author_deadline_set_by: Optional[int] = None

    class Config:
        from_attributes = True

class StatusUpdateIn(BaseModel):
    status: str
    comment: Optional[str] = None

# ✅ NUEVO: input para fijar fecha límite al autor (CORREGIDO)
class AuthorDeadlineIn(BaseModel):
    author_deadline_at: str  # 🔥 CAMBIADO de due_at a author_deadline_at para coincidir con frontend
    note: Optional[str] = None

# =========================
# Helpers (mismo estilo que admin_chapters.py)
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
# GET /dictaminador/chapters
# =========================
@router.get("/chapters", response_model=List[DictaminadorChapterOut])
def list_my_chapters(
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """Obtiene los capítulos asignados al dictaminador actual"""

    dictaminador = _require_dictaminador(db, user)

    chapters = (
        db.query(
            Chapter.id,
            Chapter.title,
            Chapter.status,
            Chapter.updated_at,
            Chapter.file_path,
            Chapter.book_id,
            Book.name.label("book_name"),
            Chapter.author_name,
            Chapter.author_email,

            # ✅ EXISTENTE: editorial -> dictaminador
            Chapter.deadline_at,
            Chapter.deadline_stage,

            # ✅ NUEVO: dictaminador -> autor
            Chapter.author_deadline_at,
            Chapter.author_deadline_set_at,
            Chapter.author_deadline_set_by,
        )
        .join(Book, Book.id == Chapter.book_id)
        .filter(Chapter.evaluator_id == dictaminador.id)
        .order_by(
            Chapter.deadline_at.asc().nulls_last(),
            Chapter.updated_at.desc()
        )
        .all()
    )

    result = []
    today = date.today()

    for c in chapters:
        days_remaining = None
        is_overdue = False

        if c.deadline_at:
            if isinstance(c.deadline_at, datetime):
                deadline_date = c.deadline_at.date()
            else:
                deadline_date = c.deadline_at
            days_remaining = (deadline_date - today).days
            is_overdue = days_remaining < 0

        result.append(DictaminadorChapterOut(
            id=c.id,
            title=c.title,
            status=c.status,
            updated_at=str(c.updated_at),
            file_path=c.file_path,
            book_name=c.book_name,
            author_name=c.author_name,
            author_email=c.author_email,

            # ✅ EXISTENTE
            deadline_at=str(c.deadline_at) if c.deadline_at else None,
            deadline_stage=c.deadline_stage,
            days_remaining=days_remaining,
            is_overdue=is_overdue,

            # ✅ NUEVO
            author_deadline_at=str(c.author_deadline_at) if c.author_deadline_at else None,
            author_deadline_set_at=str(c.author_deadline_set_at) if c.author_deadline_set_at else None,
            author_deadline_set_by=int(c.author_deadline_set_by) if c.author_deadline_set_by else None,
        ))

    return result

# =========================
# GET /dictaminador/chapters/{chapter_id}
# =========================
@router.get("/chapters/{chapter_id}", response_model=DictaminadorChapterOut)
def get_chapter_detail(
    chapter_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """Obtiene detalle de un capítulo específico"""

    dictaminador = _require_dictaminador(db, user)

    c = (
        db.query(
            Chapter.id,
            Chapter.title,
            Chapter.status,
            Chapter.updated_at,
            Chapter.file_path,
            Chapter.book_id,
            Book.name.label("book_name"),
            Chapter.author_name,
            Chapter.author_email,

            # ✅ EXISTENTE
            Chapter.deadline_at,
            Chapter.deadline_stage,

            # ✅ NUEVO
            Chapter.author_deadline_at,
            Chapter.author_deadline_set_at,
            Chapter.author_deadline_set_by,
        )
        .join(Book, Book.id == Chapter.book_id)
        .filter(
            Chapter.id == chapter_id,
            Chapter.evaluator_id == dictaminador.id
        )
        .first()
    )

    if not c:
        raise HTTPException(status_code=404, detail="Capítulo no encontrado o no asignado a ti")

    today = date.today()
    days_remaining = None
    is_overdue = False

    if c.deadline_at:
        if isinstance(c.deadline_at, datetime):
            deadline_date = c.deadline_at.date()
        else:
            deadline_date = c.deadline_at
        days_remaining = (deadline_date - today).days
        is_overdue = days_remaining < 0

    return DictaminadorChapterOut(
        id=c.id,
        title=c.title,
        status=c.status,
        updated_at=str(c.updated_at),
        file_path=c.file_path,
        book_name=c.book_name,
        author_name=c.author_name,
        author_email=c.author_email,

        # ✅ EXISTENTE
        deadline_at=str(c.deadline_at) if c.deadline_at else None,
        deadline_stage=c.deadline_stage,
        days_remaining=days_remaining,
        is_overdue=is_overdue,

        # ✅ NUEVO
        author_deadline_at=str(c.author_deadline_at) if c.author_deadline_at else None,
        author_deadline_set_at=str(c.author_deadline_set_at) if c.author_deadline_set_at else None,
        author_deadline_set_by=int(c.author_deadline_set_by) if c.author_deadline_set_by else None,
    )

# =========================
# GET /dictaminador/chapters/{chapter_id}/view-latest
# =========================
@router.get("/chapters/{chapter_id}/view-latest")
def view_latest_file(
    chapter_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """Ver el último archivo del capítulo en el navegador"""
    dictaminador = _require_dictaminador(db, user)

    chapter = db.query(Chapter).filter(
        Chapter.id == chapter_id,
        Chapter.evaluator_id == dictaminador.id
    ).first()

    if not chapter:
        raise HTTPException(status_code=404, detail="Capítulo no encontrado")

    # Determinar qué archivo mostrar (el más reciente)
    file_path = chapter.corrected_file_path or chapter.file_path

    if not file_path:
        raise HTTPException(status_code=404, detail="No hay archivo disponible")

    from fastapi.responses import FileResponse
    import os

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Archivo no encontrado en el servidor")

    return FileResponse(
        file_path,
        media_type="application/octet-stream",
        filename=os.path.basename(file_path)
    )

# =========================
# GET /dictaminador/chapters/{chapter_id}/download-latest
# =========================
@router.get("/chapters/{chapter_id}/download-latest")
def download_latest_file(
    chapter_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """Descargar el último archivo del capítulo"""
    dictaminador = _require_dictaminador(db, user)

    chapter = db.query(Chapter).filter(
        Chapter.id == chapter_id,
        Chapter.evaluator_id == dictaminador.id
    ).first()

    if not chapter:
        raise HTTPException(status_code=404, detail="Capítulo no encontrado")

    file_path = chapter.corrected_file_path or chapter.file_path

    if not file_path:
        raise HTTPException(status_code=404, detail="No hay archivo disponible")

    from fastapi.responses import FileResponse
    import os

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Archivo no encontrado en el servidor")

    return FileResponse(
        file_path,
        media_type="application/octet-stream",
        filename=os.path.basename(file_path),
        headers={"Content-Disposition": f"attachment; filename={os.path.basename(file_path)}"}
    )

# =========================
# PATCH /dictaminador/chapters/{chapter_id}/status
# =========================
@router.patch("/chapters/{chapter_id}/status")
def update_chapter_status(
    chapter_id: int,
    payload: StatusUpdateIn,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """Actualizar estado de un capítulo"""
    dictaminador = _require_dictaminador(db, user)

    chapter = db.query(Chapter).filter(
        Chapter.id == chapter_id,
        Chapter.evaluator_id == dictaminador.id
    ).first()

    if not chapter:
        raise HTTPException(status_code=404, detail="Capítulo no encontrado")

    chapter.status = payload.status
    chapter.updated_at = datetime.now()

    # Si hay comentario, podrías guardarlo en un historial
    if payload.comment and hasattr(chapter, 'history'):
        from app.models.chapter_history import ChapterHistory
        history = ChapterHistory(
            chapter_id=chapter.id,
            by=dictaminador.name,
            action=f"Cambio de estado a {payload.status}",
            detail=payload.comment,
            at=datetime.now()
        )
        db.add(history)

    db.commit()
    db.refresh(chapter)

    return {"ok": True, "status": chapter.status}

# =========================
# POST /dictaminador/chapters/{chapter_id}/author-deadline
# ✅ NUEVO: fecha límite Dictaminador -> Autor (CORREGIDO)
# =========================
@router.post("/chapters/{chapter_id}/author-deadline")
def set_author_deadline(
    chapter_id: int,
    payload: AuthorDeadlineIn,
    db: Session = Depends(get_db),
    user=Depends(get_current_user)
):
    """Fija fecha límite al autor para entregar correcciones (Dictaminador -> Autor)."""
    dictaminador = _require_dictaminador(db, user)

    chapter = db.query(Chapter).filter(
        Chapter.id == chapter_id,
        Chapter.evaluator_id == dictaminador.id
    ).first()

    if not chapter:
        raise HTTPException(status_code=404, detail="Capítulo no encontrado")

    # ✅ Regla recomendada: solo cuando está en correcciones
    if chapter.status not in ("CORRECCIONES", "CORRECCIONES_SOLICITADAS_A_AUTOR"):
        raise HTTPException(
            status_code=400,
            detail="Solo puedes fijar fecha límite al autor cuando el capítulo esté en correcciones"
        )

    try:
        # 🔥 Convertir el string a datetime
        deadline_date = datetime.strptime(payload.author_deadline_at, "%Y-%m-%d")
        
        # 1) Guardar deadline específico del autor (sin tocar deadline_* existente)
        chapter.author_deadline_at = deadline_date  # 🔥 Usar deadline_date, no payload.author_deadline_at
        chapter.author_deadline_set_at = datetime.now()
        chapter.author_deadline_set_by = dictaminador.id

        # 2) Guardar historial (reutiliza tu tabla chapter_deadlines)
        db.add(ChapterDeadline(
            chapter_id=chapter.id,
            stage="AUTOR_CORRECCIONES",
            due_at=deadline_date,
            set_by=dictaminador.id,
            note=payload.note
        ))

        db.commit()
        db.refresh(chapter)

        return {
            "ok": True, 
            "author_deadline_at": str(chapter.author_deadline_at)
        }

    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Formato de fecha inválido. Use YYYY-MM-DD"
        )