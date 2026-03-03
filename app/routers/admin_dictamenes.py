from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.db.session import get_db
from app.core.deps import get_current_user

from app.models.user import User
from app.models.dictamen import Dictamen
from app.models.chapter import Chapter
from app.models.book import Book

from app.schemas.admin_dictamenes import AdminDictamenRowOut




router = APIRouter(prefix="/admin", tags=["admin-dictamenes"])


# =========================
# Helpers (igual que los otros routers)
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
# GET /admin/dictamenes
# =========================
@router.get("/dictamenes", response_model=list[AdminDictamenRowOut])
def list_dictamenes(db: Session = Depends(get_db), user=Depends(get_current_user)):
    _require_editorial(db, user)

    # Nota: Dictamen.updated_at puede ser NULL, por eso orden extra por id
    rows = (
        db.query(Dictamen, Chapter, Book, User)
        .join(Chapter, Chapter.id == Dictamen.chapter_id)
        .join(Book, Book.id == Chapter.book_id)
        .join(User, User.id == Dictamen.evaluador_id)
        .order_by(desc(Dictamen.id))
        .all()
    )

    out: list[AdminDictamenRowOut] = []
    for d, c, b, u in rows:
        out.append(
            AdminDictamenRowOut(
                id=int(d.id),
                folio=d.folio,
                chapterFolio=getattr(c, "folio", None),  # ✅ AQUI

                capituloId=int(c.id),
                capitulo=c.title,
                libro=b.name,
                evaluador=(u.email or u.name),

                decision=d.decision,
                promedio=float(d.promedio or 0),
                status=d.status,
                updatedAt=str(d.updated_at or d.created_at),
            )
        )

    return out


# =========================
# POST /admin/dictamenes/{id}/generate-pdf
# (por ahora solo cambia status a GENERADO)
# =========================
@router.post("/dictamenes/{dictamen_id}/generate-pdf", response_model=AdminDictamenRowOut)
def generate_pdf(dictamen_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    _require_editorial(db, user)

    d = db.query(Dictamen).filter(Dictamen.id == dictamen_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Dictamen no encontrado")

    if d.status == "FIRMADO":
        raise HTTPException(status_code=400, detail="Este dictamen ya está firmado")

    # Aquí luego metes la generación real del PDF y guardas pdf_path si quieres
    d.status = "GENERADO"
    db.add(d)
    db.commit()
    db.refresh(d)

    # Re-armar la fila para el frontend
    c = db.query(Chapter).filter(Chapter.id == d.chapter_id).first()
    b = db.query(Book).filter(Book.id == c.book_id).first() if c else None
    u = db.query(User).filter(User.id == d.evaluador_id).first()

    if not c or not b or not u:
        raise HTTPException(status_code=500, detail="Relaciones incompletas (chapter/book/user)")

    return AdminDictamenRowOut(
        id=int(d.id),
        folio=d.folio,
        chapterFolio=getattr(c, "folio", None),  # ✅ AQUI
        capituloId=int(c.id),
        capitulo=c.title,
        libro=b.name,
        evaluador=(u.email or u.name),
        decision=d.decision,
        promedio=float(d.promedio or 0),
        status=d.status,
        updatedAt=str(d.updated_at or d.created_at),
    )


# =========================
# POST /admin/dictamenes/{id}/mark-signed
# (por ahora solo cambia status a FIRMADO)
# =========================
@router.post("/dictamenes/{dictamen_id}/mark-signed", response_model=AdminDictamenRowOut)
def mark_signed(dictamen_id: int, db: Session = Depends(get_db), user=Depends(get_current_user)):
    _require_editorial(db, user)

    d = db.query(Dictamen).filter(Dictamen.id == dictamen_id).first()
    if not d:
        raise HTTPException(status_code=404, detail="Dictamen no encontrado")

    if d.status == "BORRADOR":
        raise HTTPException(status_code=400, detail="Primero genera el PDF antes de firmar")

    d.status = "FIRMADO"
    db.add(d)
    db.commit()
    db.refresh(d)

    c = db.query(Chapter).filter(Chapter.id == d.chapter_id).first()
    b = db.query(Book).filter(Book.id == c.book_id).first() if c else None
    u = db.query(User).filter(User.id == d.evaluador_id).first()

    if not c or not b or not u:
        raise HTTPException(status_code=500, detail="Relaciones incompletas (chapter/book/user)")

    return AdminDictamenRowOut(
        id=int(d.id),
        folio=d.folio,
        chapterFolio=getattr(c, "folio", None),  # ✅ AQUI
        capituloId=int(c.id),
        capitulo=c.title,
        libro=b.name,
        evaluador=(u.email or u.name),
        decision=d.decision,
        promedio=float(d.promedio or 0),
        status=d.status,
        updatedAt=str(d.updated_at or d.created_at),
    )
    