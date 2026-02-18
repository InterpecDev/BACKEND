import os
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from starlette.responses import FileResponse

from app.db.session import get_db
from app.core.deps import get_current_user

from app.models.user import User
from app.models.book import Book
from app.models.chapter import Chapter
from app.models.dictamen import Dictamen
from app.models.chapter_version import ChapterVersion

from app.schemas.books import BookOut, BookCreate
from app.schemas.chapter import ChapterOut
from app.schemas.dictamen import DictamenOut

router = APIRouter(prefix="/autor", tags=["autor"])

STORAGE_DIR = os.getenv("STORAGE_DIR", "storage")
CHAPTERS_DIR = os.path.join(STORAGE_DIR, "chapters")

def _role(user_or_payload) -> Optional[str]:
    if isinstance(user_or_payload, dict):
        return user_or_payload.get("role")
    return getattr(user_or_payload, "role", None)

def _user_id(user_or_payload) -> int:
    if isinstance(user_or_payload, dict):
        # tu auth a veces trae sub, a veces id
        if user_or_payload.get("id") is not None:
            return int(user_or_payload["id"])
        if user_or_payload.get("sub") is not None:
            return int(user_or_payload["sub"])
        if user_or_payload.get("user_id") is not None:
            return int(user_or_payload["user_id"])
        raise HTTPException(status_code=401, detail="Token inválido (sin id/sub).")
    return int(user_or_payload.id)

def require_autor(user_or_payload):
    if _role(user_or_payload) != "autor":
        raise HTTPException(status_code=403, detail="Solo autor")

def public_url(path: str) -> str:
    rel = path.replace("\\", "/")
    if rel.startswith("storage/"):
        rel = rel[len("storage/"):]
    return f"/api/storage/{rel}"

def guess_media_type(ext: str) -> str:
    ext = (ext or "").lower()
    if ext == ".pdf":
        return "application/pdf"
    if ext == ".doc":
        return "application/msword"
    if ext == ".docx":
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return "application/octet-stream"

def _physical_from_public_storage_url(file_url: str) -> str:
    if not file_url:
        raise HTTPException(status_code=404, detail="Sin archivo")
    rel = file_url.replace("\\", "/")
    prefix = "/api/storage/"
    if prefix not in rel:
        raise HTTPException(status_code=500, detail="Ruta inválida en BD (no es /api/storage/...)")
    rel_storage = rel.split(prefix, 1)[1]
    return os.path.join(STORAGE_DIR, rel_storage.replace("/", os.sep))

def _add_chapter_version(db: Session, chapter_id: int, file_name: str, file_path: str, note: Optional[str] = None):
    count = db.query(ChapterVersion).filter(ChapterVersion.chapter_id == int(chapter_id)).count()
    version_label = f"V{count + 1}"
    v = ChapterVersion(
        chapter_id=int(chapter_id),
        version_label=version_label,
        file_name=(file_name or "").strip() or f"capitulo_{chapter_id}",
        file_path=(file_path or "").strip(),
        note=(note or "").strip() or None,
    )
    db.add(v)
    return version_label

@router.get("/books", response_model=list[BookOut])
def my_books(db: Session = Depends(get_db), user=Depends(get_current_user)):
    require_autor(user)
    uid = _user_id(user)

    return (
        db.query(Book)
        .filter(Book.author_id == uid)
        .order_by(Book.year.desc(), Book.id.desc())
        .all()
    )

@router.post("/books", response_model=BookOut)
def create_book(payload: BookCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    require_autor(user)
    uid = _user_id(user)

    b = Book(
        name=payload.name.strip(),
        year=int(payload.year),
        author_id=uid,
        created_at=datetime.utcnow(),
    )
    db.add(b)
    db.commit()
    db.refresh(b)
    return b

@router.get("/books/{book_id}/chapters", response_model=list[ChapterOut])
def my_book_chapters(book_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    require_autor(user)
    uid = _user_id(user)

    book = db.query(Book).filter(Book.id == book_id, Book.author_id == uid).first()
    if not book:
        raise HTTPException(status_code=404, detail="Libro no encontrado")

    return (
        db.query(Chapter)
        .filter(Chapter.book_id == book_id, Chapter.author_id == uid)
        .order_by(Chapter.updated_at.desc(), Chapter.id.desc())
        .all()
    )

@router.post("/books/{book_id}/chapters", response_model=ChapterOut)
async def upload_chapter(
    book_id: int,
    title: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    require_autor(user)
    uid = _user_id(user)

    me = db.query(User).filter(User.id == uid).first()
    if not me:
        raise HTTPException(status_code=401, detail="Usuario no encontrado")

    author_name = (me.name or "").strip() or "Autor"
    author_email = (me.email or "").strip()
    if not author_email:
        raise HTTPException(status_code=400, detail="Tu cuenta no tiene correo válido.")

    book = db.query(Book).filter(Book.id == book_id, Book.author_id == uid).first()
    if not book:
        raise HTTPException(status_code=404, detail="Libro no encontrado o no te pertenece.")

    ok_ext = (".pdf", ".doc", ".docx")
    filename = (file.filename or "").strip()
    if not filename.lower().endswith(ok_ext):
        raise HTTPException(status_code=400, detail="Formato no permitido. Sube PDF o Word (DOC/DOCX).")

    os.makedirs(CHAPTERS_DIR, exist_ok=True)

    safe_title = "".join(ch for ch in title.strip() if ch.isalnum() or ch in (" ", "-", "_")).strip()
    stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    ext = os.path.splitext(filename)[1].lower()

    out_name = f"book{book_id}_author{uid}_{stamp}_{safe_title}".replace(" ", "_") + ext
    out_path = os.path.join(CHAPTERS_DIR, out_name)

    try:
        content = await file.read()
        if not content or len(content) < 50:
            raise HTTPException(status_code=400, detail="Archivo vacío o inválido.")
        with open(out_path, "wb") as f:
            f.write(content)
    finally:
        await file.close()

    url = public_url(out_path)

    ch = Chapter(
        book_id=book_id,
        author_id=uid,
        author_name=author_name,
        author_email=author_email,
        title=title.strip(),
        file_path=url,
        status="RECIBIDO",
        updated_at=datetime.utcnow(),
    )
    db.add(ch)
    db.commit()
    db.refresh(ch)

    _add_chapter_version(db, int(ch.id), filename, url, "Versión inicial (autor)")
    db.commit()

    return ch

@router.get("/chapters/{chapter_id}/download")
def download_my_chapter(chapter_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    require_autor(user)
    uid = _user_id(user)

    ch = db.query(Chapter).filter(Chapter.id == chapter_id, Chapter.author_id == uid).first()
    if not ch:
        raise HTTPException(status_code=404, detail="Capítulo no encontrado")
    if not ch.file_path:
        raise HTTPException(status_code=404, detail="Este capítulo no tiene archivo")

    physical_path = _physical_from_public_storage_url(ch.file_path)
    if not os.path.exists(physical_path):
        raise HTTPException(status_code=404, detail="Archivo no encontrado en servidor")

    ext = os.path.splitext(physical_path)[1] or ".bin"
    media_type = guess_media_type(ext)

    safe_name = "".join(c for c in (ch.title or "capitulo") if c.isalnum() or c in (" ", "-", "_")).strip() or f"capitulo_{ch.id}"
    filename = f"{safe_name}{ext}".replace(" ", "_")

    return FileResponse(path=physical_path, media_type=media_type, filename=filename)

@router.get("/chapters/{chapter_id}/dictamenes", response_model=list[DictamenOut])
def list_dictamenes_for_chapter(chapter_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    require_autor(user)
    uid = _user_id(user)

    ch = db.query(Chapter).filter(Chapter.id == chapter_id, Chapter.author_id == uid).first()
    if not ch:
        raise HTTPException(status_code=404, detail="Capítulo no encontrado")

    return (
        db.query(Dictamen)
        .filter(Dictamen.chapter_id == chapter_id)
        .order_by(Dictamen.created_at.desc(), Dictamen.id.desc())
        .all()
    )

@router.get("/dictamenes/{dictamen_id}/download")
def download_dictamen_pdf(dictamen_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    require_autor(user)
    uid = _user_id(user)

    d = db.query(Dictamen).filter(Dictamen.id == dictamen_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Dictamen no encontrado")

    ch = db.query(Chapter).filter(Chapter.id == d.chapter_id, Chapter.author_id == uid).first()
    if not ch:
        raise HTTPException(status_code=403, detail="No autorizado")

    if not d.pdf_path:
        raise HTTPException(status_code=404, detail="Este dictamen no tiene PDF")

    physical_path = _physical_from_public_storage_url(d.pdf_path)
    if not os.path.exists(physical_path):
        raise HTTPException(status_code=404, detail="Archivo de dictamen no encontrado en servidor")

    filename = f"dictamen_{(d.folio or str(d.id)).strip()}.pdf".replace(" ", "_")
    return FileResponse(path=physical_path, media_type="application/pdf", filename=filename)

@router.post("/chapters/{chapter_id}/reupload")
async def reupload_chapter_version(
    chapter_id: int,
    file: UploadFile = File(...),
    note: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    require_autor(user)
    uid = _user_id(user)

    ch = db.query(Chapter).filter(Chapter.id == chapter_id, Chapter.author_id == uid).first()
    if not ch:
        raise HTTPException(status_code=404, detail="Capítulo no encontrado")

    ok_ext = (".pdf", ".doc", ".docx")
    filename = (file.filename or "").strip()
    if not filename.lower().endswith(ok_ext):
        raise HTTPException(status_code=400, detail="Formato no permitido. Sube PDF o Word (DOC/DOCX).")

    os.makedirs(CHAPTERS_DIR, exist_ok=True)

    stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    ext = os.path.splitext(filename)[1].lower()
    safe_title = "".join(c for c in (ch.title or "capitulo") if c.isalnum() or c in (" ", "-", "_")).strip()
    out_name = f"chapter{chapter_id}_author{uid}_reupload_{stamp}_{safe_title}".replace(" ", "_") + ext
    out_path = os.path.join(CHAPTERS_DIR, out_name)

    try:
        content = await file.read()
        if not content or len(content) < 50:
            raise HTTPException(status_code=400, detail="Archivo vacío o inválido.")
        with open(out_path, "wb") as f:
            f.write(content)
    finally:
        await file.close()

    new_url = public_url(out_path)

    ch.corrected_file_path = new_url
    ch.corrected_updated_at = datetime.utcnow()
    ch.status = "REENVIADO_POR_AUTOR"
    ch.updated_at = datetime.utcnow()

    _add_chapter_version(
        db=db,
        chapter_id=int(ch.id),
        file_name=filename,
        file_path=new_url,
        note=(note or "").strip() or "Reenvío de corrección (autor)",
    )

    db.add(ch)
    db.commit()

    return {"ok": True, "chapter_id": int(ch.id), "file_path": new_url, "note": (note or "").strip() or None}