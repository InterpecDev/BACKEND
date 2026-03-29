# app/routers/admin_dictamen_documento.py
import os
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.deps import get_current_user  # <- tu auth existente
from app.models.user import User
from app.models.dictamen import Dictamen
from app.models.chapter import Chapter
from app.models.book import Book

from app.schemas.admin_dictamen_documento import (
    AdminDictamenDocumentoOut,
    AdminDictamenDocumentoUpdateIn,
)

from app.services.dictamen_document_service import (
    ensure_dir,
    save_upload_to_disk,
    render_docx_from_template,
    convert_docx_to_pdf_libreoffice,
    build_context,
    unique_filename,
)

router = APIRouter(prefix="/admin/dictamenes", tags=["admin-dictamen-documento"])

UPLOAD_ROOT = os.getenv("UPLOAD_ROOT", "uploads")
TEMPLATE_DIR = os.path.join(UPLOAD_ROOT, "dictamen_templates")
GENERATED_DIR = os.path.join(UPLOAD_ROOT, "dictamen_generated")
ensure_dir(TEMPLATE_DIR)
ensure_dir(GENERATED_DIR)


# ✅ Rol blindado (dict u ORM, enum u string)
def _normalize_role(role_value) -> str:
    if role_value is None:
        return ""
    if hasattr(role_value, "value"):
        try:
            return str(role_value.value).strip().lower()
        except Exception:
            pass
    s = str(role_value).strip().lower()
    if "." in s:
        s = s.split(".")[-1]
    return s


def require_editorial(user):
    role_raw = user.get("role") if isinstance(user, dict) else getattr(user, "role", None)
    role = _normalize_role(role_raw)
    if role != "editorial":
        raise HTTPException(status_code=403, detail="No autorizado (solo editorial).")


def dictamen_or_404(db: Session, dictamen_id: int) -> Dictamen:
    d = db.query(Dictamen).filter(Dictamen.id == dictamen_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Dictamen no encontrado.")
    return d


def build_detail(db: Session, d: Dictamen) -> AdminDictamenDocumentoOut:
    ch = db.query(Chapter).filter(Chapter.id == d.chapter_id).first()
    if not ch:
        raise HTTPException(status_code=500, detail="Capítulo asociado no encontrado.")

    bk = db.query(Book).filter(Book.id == ch.book_id).first()
    libro_name = bk.name if bk else "—"

    ev = db.query(User).filter(User.id == d.evaluador_id).first()
    evaluador_name = ev.name if ev else "—"
    
    
    #NUEVOS
    evaluador_institucion = ev.institution if ev else None
    evaluador_cvo_snii = ev.cvo_snii if ev else None


    return AdminDictamenDocumentoOut(
        id=int(d.id),
        folio=d.folio,
        chapterFolio=getattr(ch, "folio", None),  # ✅ folio del capítulo
        status=d.status,

        template_docx_path=d.template_docx_path,
        generated_docx_path=d.generated_docx_path,
        pdf_path=d.pdf_path,

        recipient_name=d.recipient_name,
        constancia_data_json=d.constancia_data_json,

        capituloId=int(ch.id),
        capitulo=ch.title,
        libro=libro_name,
        evaluador=evaluador_name,
        
        # ✅ nuevos
    evaluador_institucion=evaluador_institucion,
    evaluador_cvo_snii=evaluador_cvo_snii,
    )


@router.get("/{dictamen_id}", response_model=AdminDictamenDocumentoOut)
def get_dictamen_documento(
    dictamen_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    require_editorial(user)
    d = dictamen_or_404(db, dictamen_id)
    return build_detail(db, d)


@router.post("/{dictamen_id}/template")
def upload_template(
    dictamen_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    require_editorial(user)
    d = dictamen_or_404(db, dictamen_id)

    if not file.filename.lower().endswith(".docx"):
        raise HTTPException(status_code=400, detail="Solo se acepta .docx")

    fname = unique_filename(f"template-dictamen-{d.id}", "docx")
    dest_path = os.path.join(TEMPLATE_DIR, fname)
    save_upload_to_disk(file, dest_path)

    d.template_docx_path = dest_path
    d.updated_at = datetime.utcnow()
    db.add(d)
    db.commit()

    return {"ok": True, "template_docx_path": dest_path}


@router.put("/{dictamen_id}/document-data")
def update_document_data(
    dictamen_id: int,
    payload: AdminDictamenDocumentoUpdateIn,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    require_editorial(user)
    d = dictamen_or_404(db, dictamen_id)

    if payload.recipient_name is not None:
        d.recipient_name = payload.recipient_name

    if payload.data is not None:
        d.constancia_data_json = payload.data

    d.updated_at = datetime.utcnow()
    db.add(d)
    db.commit()

    return {"ok": True}


@router.post("/{dictamen_id}/render-document")
def render_document(
    dictamen_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    require_editorial(user)
    d = dictamen_or_404(db, dictamen_id)

    if not d.template_docx_path or not os.path.exists(d.template_docx_path):
        raise HTTPException(status_code=400, detail="No hay plantilla DOCX subida.")

    out_docx = os.path.join(GENERATED_DIR, unique_filename(f"dictamen-{d.folio}", "docx"))

    ctx = build_context(
        folio=d.folio,
        recipient_name=d.recipient_name,
        data_json=d.constancia_data_json,
    )

    try:
        render_docx_from_template(d.template_docx_path, out_docx, ctx)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al renderizar DOCX: {str(e)}")

    d.generated_docx_path = out_docx

    # PDF opcional (si no hay LibreOffice, no truena)
    try:
        out_pdf = convert_docx_to_pdf_libreoffice(out_docx, GENERATED_DIR)
        d.pdf_path = out_pdf
    except Exception:
        # no rompas el flujo si no hay LibreOffice
        pass

    d.status = "GENERADO"
    d.updated_at = datetime.utcnow()
    db.add(d)
    db.commit()

    return {"ok": True, "status": d.status}


@router.get("/{dictamen_id}/download")
def download_document(
    dictamen_id: int,
    format: str = Query("pdf", pattern="^(pdf|docx)$"),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    require_editorial(user)
    d = dictamen_or_404(db, dictamen_id)

    if format == "docx":
        path = d.generated_docx_path
        if not path or not os.path.exists(path):
            raise HTTPException(status_code=404, detail="DOCX no disponible. Genera el documento primero.")
        return FileResponse(
            path,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename=f"dictamen-{d.folio}.docx",
        )

    path = d.pdf_path
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="PDF no disponible. Genera el documento primero.")
    return FileResponse(path, media_type="application/pdf", filename=f"dictamen-{d.folio}.pdf")