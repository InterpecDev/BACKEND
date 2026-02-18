from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime

from app.db.session import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.chapter import Chapter
from app.models.book import Book

router = APIRouter(prefix="/chapters", tags=["editorial-actions"])

def require_editorial(user: User):
    if user.role != "editorial":
        raise HTTPException(status_code=403, detail="Solo editorial puede realizar esta acción.")

@router.post("/{chapter_id}/assign-evaluator")
def assign_evaluator(chapter_id: int, payload: dict, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    require_editorial(me)

    evaluator_email = (payload.get("evaluator_email") or "").strip().lower()
    if not evaluator_email:
        raise HTTPException(status_code=400, detail="Falta evaluator_email")

    ch = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    if not ch:
        raise HTTPException(status_code=404, detail="Capítulo no encontrado")

    u = db.query(User).filter(User.email == evaluator_email).first()
    if not u or u.role != "dictaminador":
        raise HTTPException(status_code=400, detail="El correo no corresponde a un dictaminador registrado")

    # Requiere columnas nuevas: evaluator_id/evaluator_name/evaluator_email (si no las tienes, dime y lo adapto)
    ch.evaluator_id = u.id
    ch.evaluator_name = u.name
    ch.evaluator_email = u.email
    ch.status = "ASIGNADO_A_DICTAMINADOR"
    ch.updated_at = datetime.utcnow()

    db.add(ch)
    db.commit()

    return {"ok": True}


@router.post("/{chapter_id}/send-to-evaluator")
def send_to_evaluator(chapter_id: int, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    require_editorial(me)

    ch = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    if not ch:
        raise HTTPException(status_code=404, detail="Capítulo no encontrado")

    if not getattr(ch, "evaluator_email", None):
        raise HTTPException(status_code=400, detail="Este capítulo no tiene dictaminador asignado")

    book = db.query(Book).filter(Book.id == ch.book_id).first()

    # ✅ Aquí tú después conectas:
    # - envío real por SMTP / proveedor
    # - registro en historial
    # Por ahora solo confirmamos que hay email y devolvemos info útil
    return {
        "ok": True,
        "to": ch.evaluator_email,
        "subject": f"Capítulo asignado para dictamen — {book.name if book else 'Libro'} — {ch.title}",
        "chapter_id": ch.id,
    }
