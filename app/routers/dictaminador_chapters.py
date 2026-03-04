# app/routers/dictaminador_chapters.py
import os
import uuid
from datetime import datetime, date
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.deps import get_current_user

from app.models.user import User
from app.models.book import Book
from app.models.chapter import Chapter
from app.models.dictamen import Dictamen
from app.models.chapter_deadline import ChapterDeadline

from pydantic import BaseModel

router = APIRouter(prefix="/dictaminador", tags=["dictaminador-chapters"])

# -------------------------
# Helpers (compatibles con tu auth)
# -------------------------
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
    # Ajusta aquí si tu rol real es "DICTAMINADOR" o similar
    if str(me.role).lower() not in ("dictaminador", "dictaminador_regional", "evaluator"):
        # Si solo usas "dictaminador", deja: if me.role != "dictaminador":
        if me.role != "dictaminador":
            raise HTTPException(status_code=403, detail="No autorizado (solo dictaminador)")
    return me


# -------------------------
# Config/constantes
# -------------------------
ALLOWED = {
    "RECIBIDO",
    "ASIGNADO_A_DICTAMINADOR",
    "EN_REVISION",
    "CORRECCIONES",
    "REENVIADO_POR_AUTOR",
    "APROBADO",
    "RECHAZADO",
    "FIRMADO",
}

STORAGE_DIR = os.getenv("STORAGE_DIR", "storage")
CHAPTERS_DIR = os.path.join(STORAGE_DIR, "chapters")
DICTAMENES_DIR = os.path.join(STORAGE_DIR, "dictamenes")


def _gen_folio() -> str:
    return f"DICT-{uuid.uuid4().hex[:10].upper()}"


def _guess_media_type(ext: str) -> str:
    ext = (ext or "").lower()
    if ext == ".pdf":
        return "application/pdf"
    if ext == ".doc":
        return "application/msword"
    if ext == ".docx":
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return "application/octet-stream"


def _physical_from_public_storage_url(file_url: str) -> str:
    """
    Convierte:
      "/api/storage/chapters/x.pdf" -> "storage/chapters/x.pdf"
    Si NO es url pública, regresa tal cual.
    """
    rel = (file_url or "").replace("\\", "/").strip()
    prefix = "/api/storage/"
    if prefix not in rel:
        return rel
    rel_storage = rel.split(prefix, 1)[1]
    return os.path.join(STORAGE_DIR, rel_storage.replace("/", os.sep))


def _public_url_from_abs_storage_path(abs_path: str) -> str:
    """
    "storage/dictamenes/x.pdf" -> "/api/storage/dictamenes/x.pdf"
    """
    rel = abs_path.replace("\\", "/")
    if rel.startswith("storage/"):
        rel = rel[len("storage/"):]
    return f"/api/storage/{rel}"


def _pick_latest_file_path(ch: Chapter) -> str:
    corrected = (getattr(ch, "corrected_file_path", None) or "").strip()
    if corrected:
        return corrected
    return (getattr(ch, "file_path", "") or "").strip()


def _resolve_existing_path(path_or_url: str) -> str:
    """
    Acepta:
      - "/api/storage/chapters/x.pdf"
      - "storage/chapters/x.pdf"
      - "/abs/path/..."
    Devuelve path físico existente.
    """
    p = (path_or_url or "").strip()
    if not p:
        return ""

    physical = _physical_from_public_storage_url(p)

    # Si es relativo, lo convertimos a absoluto con cwd
    if not os.path.isabs(physical):
        physical = os.path.join(os.getcwd(), physical)

    # Normaliza
    physical = os.path.normpath(physical)

    return physical


# -------------------------
# Schemas (respuesta compatible con tu frontend)
# -------------------------
class DictChapterRowOut(BaseModel):
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


class DictChapterStatusUpdateIn(BaseModel):
    status: str
    comment: Optional[str] = None
    # ✅ opcional: si tu frontend lo manda aquí, lo guardamos
    author_deadline_at: Optional[str] = None  # "YYYY-MM-DD"


class AuthorDeadlineIn(BaseModel):
    author_deadline_at: str  # "YYYY-MM-DD"
    note: Optional[str] = None


def _compute_deadline_meta(deadline_at_val) -> tuple[Optional[int], bool]:
    """
    days_remaining, is_overdue
    """
    if not deadline_at_val:
        return None, False

    today = date.today()

    if isinstance(deadline_at_val, datetime):
        d = deadline_at_val.date()
    else:
        d = deadline_at_val  # date

    days = (d - today).days
    return days, (days < 0)


# ============================================================
# ✅ GET /api/dictaminador/chapters
# ============================================================
@router.get("/chapters", response_model=List[DictChapterRowOut])
def list_my_assigned_chapters(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    me = _require_dictaminador(db, user)

    rows = (
        db.query(Chapter, Book)
        .join(Book, Book.id == Chapter.book_id)
        .filter(Chapter.evaluator_id == me.id)
        .order_by(Chapter.updated_at.desc(), Chapter.id.desc())
        .all()
    )

    out: List[DictChapterRowOut] = []
    for ch, b in rows:
        days_remaining, is_overdue = _compute_deadline_meta(getattr(ch, "deadline_at", None))

        out.append(
            DictChapterRowOut(
                id=int(ch.id),
                title=ch.title,
                status=str(ch.status),
                updated_at=ch.updated_at.isoformat() if ch.updated_at else "",

                book_name=b.name if b else None,
                author_name=getattr(ch, "author_name", None),
                author_email=getattr(ch, "author_email", None),

                file_path=getattr(ch, "file_path", None),
                corrected_file_path=getattr(ch, "corrected_file_path", None),
                corrected_updated_at=(
                    ch.corrected_updated_at.isoformat()
                    if getattr(ch, "corrected_updated_at", None)
                    else None
                ),

                deadline_at=(
                    ch.deadline_at.isoformat()
                    if getattr(ch, "deadline_at", None)
                    else None
                ),
                deadline_stage=getattr(ch, "deadline_stage", None),
                days_remaining=days_remaining,
                is_overdue=is_overdue,

                author_deadline_at=(
                    ch.author_deadline_at.isoformat()
                    if getattr(ch, "author_deadline_at", None)
                    else None
                ),
                author_deadline_set_at=(
                    ch.author_deadline_set_at.isoformat()
                    if getattr(ch, "author_deadline_set_at", None)
                    else None
                ),
                author_deadline_set_by=(
                    int(ch.author_deadline_set_by)
                    if getattr(ch, "author_deadline_set_by", None)
                    else None
                ),
            )
        )

    return out


# ============================================================
# ✅ PATCH /api/dictaminador/chapters/{id}/status
# ============================================================
@router.patch("/chapters/{chapter_id}/status", response_model=DictChapterRowOut)
def update_my_chapter_status(
    chapter_id: int,
    payload: DictChapterStatusUpdateIn,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    me = _require_dictaminador(db, user)

    new_status = (payload.status or "").strip().upper()
    if new_status not in ALLOWED:
        raise HTTPException(status_code=400, detail="Estado inválido")

    ch = (
        db.query(Chapter)
        .filter(Chapter.id == chapter_id)
        .filter(Chapter.evaluator_id == me.id)
        .first()
    )
    if not ch:
        raise HTTPException(status_code=403, detail="No tienes asignado este capítulo")

    comment = (payload.comment or "").strip()
    if new_status in ("CORRECCIONES", "RECHAZADO") and not comment:
        raise HTTPException(status_code=400, detail="Escribe el comentario para Correcciones/Rechazado")

    ch.status = new_status

    # ✅ Si te mandan author_deadline_at aquí (opcional), lo guardamos
    if payload.author_deadline_at:
        try:
            deadline_date = datetime.strptime(payload.author_deadline_at, "%Y-%m-%d")
            ch.author_deadline_at = deadline_date
            ch.author_deadline_set_at = datetime.utcnow()
            ch.author_deadline_set_by = int(me.id)

            db.add(ChapterDeadline(
                chapter_id=int(ch.id),
                stage="AUTOR_CORRECCIONES",
                due_at=deadline_date,
                set_by=int(me.id),
                note="(set via PATCH status)"
            ))
        except ValueError:
            raise HTTPException(status_code=400, detail="Formato de fecha inválido. Use YYYY-MM-DD")

    # ✅ Guardar comentario como Dictamen
    if comment:
        decision = "CORRECCIONES" if new_status == "CORRECCIONES" else "RECHAZADO"

        existing = (
            db.query(Dictamen)
            .filter(Dictamen.chapter_id == int(ch.id))
            .filter(Dictamen.evaluador_id == int(me.id))
            .first()
        )

        if existing:
            existing.decision = decision
            existing.status = "GENERADO"
            existing.comentarios = comment
            existing.tipo = "INVESTIGACION"
            existing.updated_at = datetime.utcnow()
            db.add(existing)
        else:
            d = Dictamen(
                folio=_gen_folio(),
                chapter_id=int(ch.id),
                evaluador_id=int(me.id),
                tipo="INVESTIGACION",
                decision=decision,
                status="GENERADO",
                comentarios=comment,
            )
            db.add(d)

    ch.updated_at = datetime.utcnow()
    db.add(ch)
    db.commit()
    db.refresh(ch)

    b = db.query(Book).filter(Book.id == ch.book_id).first()
    days_remaining, is_overdue = _compute_deadline_meta(getattr(ch, "deadline_at", None))

    return DictChapterRowOut(
        id=int(ch.id),
        title=ch.title,
        status=str(ch.status),
        updated_at=ch.updated_at.isoformat() if ch.updated_at else "",

        book_name=b.name if b else None,
        author_name=getattr(ch, "author_name", None),
        author_email=getattr(ch, "author_email", None),

        file_path=getattr(ch, "file_path", None),
        corrected_file_path=getattr(ch, "corrected_file_path", None),
        corrected_updated_at=(
            ch.corrected_updated_at.isoformat()
            if getattr(ch, "corrected_updated_at", None)
            else None
        ),

        deadline_at=(ch.deadline_at.isoformat() if getattr(ch, "deadline_at", None) else None),
        deadline_stage=getattr(ch, "deadline_stage", None),
        days_remaining=days_remaining,
        is_overdue=is_overdue,

        author_deadline_at=(ch.author_deadline_at.isoformat() if getattr(ch, "author_deadline_at", None) else None),
        author_deadline_set_at=(ch.author_deadline_set_at.isoformat() if getattr(ch, "author_deadline_set_at", None) else None),
        author_deadline_set_by=(int(ch.author_deadline_set_by) if getattr(ch, "author_deadline_set_by", None) else None),
    )


# ============================================================
# ✅ POST /api/dictaminador/chapters/{id}/author-deadline
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
        .filter(Chapter.id == chapter_id)
        .filter(Chapter.evaluator_id == me.id)
        .first()
    )
    if not ch:
        raise HTTPException(status_code=404, detail="Capítulo no encontrado o no asignado a ti")

    # Recomendado: solo permitir cuando está en correcciones
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
# ✅ GET /api/dictaminador/chapters/{id}/download (original)
# ============================================================
@router.get("/chapters/{chapter_id}/download")
def download_my_assigned_chapter_file(
    chapter_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    me = _require_dictaminador(db, user)

    ch = (
        db.query(Chapter)
        .filter(Chapter.id == chapter_id)
        .filter(Chapter.evaluator_id == me.id)
        .first()
    )
    if not ch:
        raise HTTPException(status_code=404, detail="Capítulo no encontrado o no asignado a ti")

    file_path = (getattr(ch, "file_path", "") or "").strip()
    if not file_path:
        raise HTTPException(status_code=404, detail="Este capítulo no tiene archivo")

    physical_path = _resolve_existing_path(file_path)
    if not physical_path or not os.path.exists(physical_path):
        raise HTTPException(status_code=404, detail=f"Archivo no encontrado en servidor: {file_path}")

    ext = os.path.splitext(physical_path)[1] or ".bin"
    media_type = _guess_media_type(ext)

    safe_title = "".join(c for c in (ch.title or f"capitulo_{ch.id}") if c.isalnum() or c in (" ", "-", "_")).strip()
    if not safe_title:
        safe_title = f"capitulo_{ch.id}"
    filename = f"{safe_title}{ext}".replace(" ", "_")

    return FileResponse(path=physical_path, media_type=media_type, filename=filename)


# ============================================================
# ✅ GET /api/dictaminador/chapters/{id}/download-latest
# ============================================================
@router.get("/chapters/{chapter_id}/download-latest")
def download_my_assigned_chapter_latest_file(
    chapter_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    me = _require_dictaminador(db, user)

    ch = (
        db.query(Chapter)
        .filter(Chapter.id == chapter_id)
        .filter(Chapter.evaluator_id == me.id)
        .first()
    )
    if not ch:
        raise HTTPException(status_code=404, detail="Capítulo no encontrado o no asignado a ti")

    latest_path = _pick_latest_file_path(ch)
    if not latest_path:
        raise HTTPException(status_code=404, detail="Este capítulo no tiene archivo")

    physical_path = _resolve_existing_path(latest_path)
    if not physical_path or not os.path.exists(physical_path):
        raise HTTPException(status_code=404, detail=f"Archivo no encontrado en servidor: {latest_path}")

    ext = os.path.splitext(physical_path)[1] or ".bin"
    media_type = _guess_media_type(ext)

    safe_title = "".join(c for c in (ch.title or f"capitulo_{ch.id}") if c.isalnum() or c in (" ", "-", "_")).strip()
    if not safe_title:
        safe_title = f"capitulo_{ch.id}"

    is_corrected = bool((getattr(ch, "corrected_file_path", None) or "").strip())
    suffix = "_CORREGIDO" if is_corrected else ""
    filename = f"{safe_title}{suffix}{ext}".replace(" ", "_")

    return FileResponse(path=physical_path, media_type=media_type, filename=filename)


# ============================================================
# ✅ GET /api/dictaminador/chapters/{id}/view-latest
# ============================================================
@router.get("/chapters/{chapter_id}/view-latest")
def view_my_assigned_chapter_latest_file(
    chapter_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    me = _require_dictaminador(db, user)

    ch = (
        db.query(Chapter)
        .filter(Chapter.id == chapter_id)
        .filter(Chapter.evaluator_id == me.id)
        .first()
    )
    if not ch:
        raise HTTPException(status_code=404, detail="Capítulo no encontrado o no asignado a ti")

    latest_path = _pick_latest_file_path(ch)
    if not latest_path:
        raise HTTPException(status_code=404, detail="Este capítulo no tiene archivo")

    physical_path = _resolve_existing_path(latest_path)
    if not physical_path or not os.path.exists(physical_path):
        raise HTTPException(status_code=404, detail=f"Archivo no encontrado en servidor: {latest_path}")

    ext = os.path.splitext(physical_path)[1] or ".bin"
    media_type = _guess_media_type(ext)

    # inline
    return FileResponse(
        path=physical_path,
        media_type=media_type,
        headers={"Content-Disposition": f'inline; filename="{os.path.basename(physical_path)}"'},
    )


# ============================================================
# ✅ POST /api/dictaminador/dictamenes/{id}/upload-signed
# Dictaminador sube PDF firmado y lo regresa a editorial
# ============================================================
@router.post("/dictamenes/{dictamen_id}/upload-signed")
async def upload_signed_dictamen_pdf(
    dictamen_id: int,
    file: UploadFile = File(...),
    note: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    me = _require_dictaminador(db, user)

    d = (
        db.query(Dictamen)
        .filter(Dictamen.id == dictamen_id)
        .filter(Dictamen.evaluador_id == int(me.id))
        .first()
    )
    if not d:
        raise HTTPException(status_code=404, detail="Dictamen no encontrado o no te pertenece")

    filename = (file.filename or "").strip()
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Solo se permite subir PDF firmado")

    os.makedirs(DICTAMENES_DIR, exist_ok=True)

    stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    folio = (d.folio or f"DICTAMEN_{d.id}").replace(" ", "_")
    out_name = f"DICTAMEN_FIRMADO_{folio}_{stamp}.pdf"
    out_path = os.path.join(DICTAMENES_DIR, out_name)

    try:
        content = await file.read()
        if not content or len(content) < 200:
            raise HTTPException(status_code=400, detail="Archivo vacío o inválido")
        with open(out_path, "wb") as f:
            f.write(content)
    finally:
        await file.close()

    public_url = _public_url_from_abs_storage_path(out_path)

    # Guardar en signed_pdf_path si existe; si no, sobreescribe pdf_path (compatibilidad)
    if hasattr(d, "signed_pdf_path"):
        setattr(d, "signed_pdf_path", public_url)
    else:
        d.pdf_path = public_url

    d.status = "FIRMADO"
    d.signed_at = datetime.utcnow()
    d.updated_at = datetime.utcnow()

    # Actualizar capítulo (si tu enum lo soporta)
    ch = db.query(Chapter).filter(Chapter.id == int(d.chapter_id)).first()
    if ch:
        try:
            ch.status = "FIRMADO"
        except Exception:
            pass
        ch.updated_at = datetime.utcnow()
        db.add(ch)

    if note:
        prev = (d.comentarios or "").strip()
        extra = f"\n\n[FIRMA] {note.strip()}"
        d.comentarios = (prev + extra).strip() if prev else extra.strip()

    db.add(d)
    db.commit()

    return {
        "ok": True,
        "dictamen_id": int(d.id),
        "signed_pdf_path": public_url,
        "status": d.status,
    }