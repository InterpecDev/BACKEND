from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.user import User

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/dictaminadores/by-email")
def find_dictaminador_by_email(email: str, db: Session = Depends(get_db)):
    u = db.query(User).filter(User.email == email).first()
    if not u or u.role != "dictaminador":
        raise HTTPException(status_code=404, detail="Dictaminador no encontrado con ese correo.")
    return {
        "id": u.id,
        "name": u.name,
        "email": u.email,
        "role": u.role,
        "institution": u.institution,
        "cvo_snii": u.cvo_snii,
    }
