from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import LoginIn, LoginOut
from app.core.security import verify_password, create_access_token
from app.core.deps import get_current_user  # ✅ NUEVO

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginOut)
def login(payload: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email).first()

    if not user or int(user.active) != 1:
        raise HTTPException(status_code=401, detail="Credenciales inválidas.")

    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Credenciales inválidas.")

    token = create_access_token(
        sub=str(user.id),
        extra={"role": user.role, "email": user.email}
    )

    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": int(user.id),
            "name": user.name,
            "email": user.email,
            "role": user.role
        }
    }


# ✅ NUEVO: endpoint protegido para validar token y recuperar usuario
@router.get("/me")
def me(payload=Depends(get_current_user), db: Session = Depends(get_db)):
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token inválido.")

    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user or int(user.active) != 1:
        raise HTTPException(status_code=401, detail="Usuario no válido.")

    # Si NO quieres permitir autor en plataforma:
    if user.role not in ("editorial", "dictaminador", "autor"):
        raise HTTPException(status_code=403, detail="Rol no permitido.")

    return {
        "id": int(user.id),
        "name": user.name,
        "email": user.email,
        "role": user.role
    }
