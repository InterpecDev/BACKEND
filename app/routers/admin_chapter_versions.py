import os
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.deps import get_current_user

from app.models.user import User
from app.models.chapter import Chapter
from app.models.book import Book
from app.models.chapter_version import ChapterVersion

router = APIRouter(prefix="/admin", tags=["admin-chapter-versions"])

STORAGE_DIR = os.getenv("STORAGE_DIR", "storage")


# -------------------------
# Auth mínima: solo editorial
# (no toca tu auth actual, solo valida role)
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

    raise HTTPException(status_code=401, detail="Token inválido")


def _require_editorial(db: Session, user_or_payload) -> User:
    uid = _user_id(db, user_or_payload)
    me = db.query(User).filter(User.id == uid).first()
    if not me:
        raise HTTPException(status_code=401, detail="Usuario no encontrado")
    if me.role != "editorial":
        raise HTTPException(status_code=403, detail="No autorizado (solo editorial)")
    return me


# -------------------------
# Helpers archivos (igual estilo que tu dictaminador)
# -------------------------
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
      "/api/storage/chapters/x.docx" -> "storage/chapters/x.docx"
    Si NO es url pública, regresa tal cual (por si guardaste un path físico)
    """
    rel = (file_url or "").replace("\\", "/").strip()
    prefix = "/api/storage/"
    if prefix not in rel:
        return rel
    rel_storage = rel.split(prefix, 1)[1]  # "chapters/x.docx"
    return os.path.join(STORAGE_DIR, rel_storage.replace("/", os.sep))


def _abs_path(p: str) -> str:
    if not os.path.isabs(p):
        return os.path.join(os.getcwd(), p)
    return p


# ============================================================
# ✅ GET /api/admin/chapters/{id}  (detalle + versions)
#    (AGREGA versions sin romper tu endpoint actual)
# ============================================================
@router.get("/chapters/{chapter_id}")
def admin_chapter_detail_with_versions(
    chapter_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    _require_editorial(db, user)

    ch = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    if not ch:
        raise HTTPException(status_code=404, detail="Capítulo no encontrado")

    b = db.query(Book).filter(Book.id == ch.book_id).first()

    vers = (
        db.query(ChapterVersion)
        .filter(ChapterVersion.chapter_id == chapter_id)
        .order_by(ChapterVersion.uploaded_at.desc(), ChapterVersion.id.desc())
        .all()
    )

    # ✅ respuesta simple compatible con tu mapper del front (mapChapterResponseToChapter)
    return {
        "id": int(ch.id),
        "folio": getattr(ch, "folio", None),
        "title": ch.title,
        "status": str(ch.status),
        "updated_at": ch.updated_at.isoformat() if ch.updated_at else None,

        "book_name": b.name if b else None,
        "author_name": getattr(ch, "author_name", None),
        "author_email": getattr(ch, "author_email", None),

        "evaluator_name": getattr(ch, "evaluator_name", None),
        "evaluator_email": getattr(ch, "evaluator_email", None),

        "versions": [
            {
                "id": int(v.id),
                "version_label": v.version_label,
                "file_name": v.file_name,
                "file_path": v.file_path,
                "note": v.note,
                "uploaded_at": v.uploaded_at.isoformat() if v.uploaded_at else None,
                "uploaded_by": "autor",  # si luego lo agregas a BD, aquí lo cambias
            }
            for v in vers
        ],
        "dictamenes": [],     # si ya lo tienes en otro endpoint, luego lo conectamos
        "history": [],
        "constancias": [],
    }


# ============================================================
# ✅ GET /api/admin/chapters/{id}/versions (opcional)
# ============================================================
@router.get("/chapters/{chapter_id}/versions")
def list_admin_chapter_versions(
    chapter_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    _require_editorial(db, user)

    exists = db.query(Chapter.id).filter(Chapter.id == chapter_id).first()
    if not exists:
        raise HTTPException(status_code=404, detail="Capítulo no encontrado")

    vers = (
        db.query(ChapterVersion)
        .filter(ChapterVersion.chapter_id == chapter_id)
        .order_by(ChapterVersion.uploaded_at.desc(), ChapterVersion.id.desc())
        .all()
    )

    return [
        {
            "id": int(v.id),
            "version_label": v.version_label,
            "file_name": v.file_name,
            "file_path": v.file_path,
            "note": v.note,
            "uploaded_at": v.uploaded_at.isoformat() if v.uploaded_at else None,
            "uploaded_by": "autor",
        }
        for v in vers
    ]


# ============================================================
# ✅ GET /api/admin/chapters/{id}/versions/{versionId}/download
# ============================================================
@router.get("/chapters/{chapter_id}/versions/{version_id}/download")
def download_admin_chapter_version(
    chapter_id: int,
    version_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    _require_editorial(db, user)

    v = (
        db.query(ChapterVersion)
        .filter(ChapterVersion.id == version_id)
        .filter(ChapterVersion.chapter_id == chapter_id)
        .first()
    )
    if not v:
        raise HTTPException(status_code=404, detail="Versión no encontrada")

    physical = _abs_path(_physical_from_public_storage_url(v.file_path))
    if not os.path.exists(physical):
        raise HTTPException(
            status_code=404,
            detail=f"Archivo no encontrado. file_path='{v.file_path}' resolved='{physical}'"
        )

    ext = os.path.splitext(physical)[1] or ".bin"
    media_type = _guess_media_type(ext)

    filename = (v.file_name or f"version_{v.id}{ext}").replace(" ", "_")

    return FileResponse(
        path=physical,
        media_type=media_type,
        filename=filename,
    )