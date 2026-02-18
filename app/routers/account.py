from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.user_preferences import UserPreferences
from app.models.user_privacy import UserPrivacy
from app.schemas.account import (
    AccountMeOut, AccountMeUpdate,
    ChangePasswordIn,
    PreferencesOut, PreferencesUpdate,
    PrivacyOut, PrivacyUpdate
)

from app.core.security import verify_password, hash_password

router = APIRouter(prefix="/account", tags=["account"])


# =========================
# ✅ PARCHE: soportar sub como ID o como EMAIL
# =========================
def _user_id(db: Session, user_or_payload) -> int:
    """
    Soporta:
    - get_current_user devuelve User (SQLAlchemy)
    - get_current_user devuelve dict con: id / user_id / sub (id o email)
    """

    # Caso 1: ya viene como modelo User
    if not isinstance(user_or_payload, dict):
        return int(user_or_payload.id)

    # Caso 2: dict trae id directo
    if user_or_payload.get("id") is not None:
        return int(user_or_payload["id"])

    if user_or_payload.get("user_id") is not None:
        return int(user_or_payload["user_id"])

    # Caso 3: dict trae sub
    sub = user_or_payload.get("sub")

    # sub puede ser número
    if isinstance(sub, int):
        return int(sub)

    if isinstance(sub, str) and sub.isdigit():
        return int(sub)

    # sub puede ser email
    if isinstance(sub, str) and "@" in sub:
        u = db.query(User).filter(User.email == sub.strip().lower()).first()
        if not u:
            raise HTTPException(status_code=401, detail="Usuario no encontrado")
        return int(u.id)

    raise HTTPException(status_code=401, detail="Token inválido (sin id/sub válido)")


def _require_user(db: Session, user_or_payload) -> User:
    uid = _user_id(db, user_or_payload)
    me = db.query(User).filter(User.id == uid).first()
    if not me:
        raise HTTPException(status_code=401, detail="Usuario no encontrado")
    return me


# =========================
# ME
# =========================
@router.get("/me", response_model=AccountMeOut)
def me(db: Session = Depends(get_db), user=Depends(get_current_user)):
    me = _require_user(db, user)
    return me


@router.patch("/me", response_model=AccountMeOut)
def update_me(payload: AccountMeUpdate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    me = _require_user(db, user)

    if payload.name is not None:
        name = payload.name.strip()
        if len(name) < 2:
            raise HTTPException(status_code=400, detail="Nombre inválido")
        me.name = name

    # OJO: si NO quieres permitir cambiar correo, elimina este bloque
    if payload.email is not None:
        email = payload.email.strip().lower()
        if not email or "@" not in email:
            raise HTTPException(status_code=400, detail="Correo inválido")
        me.email = email

    db.add(me)
    db.commit()
    db.refresh(me)
    return me


# =========================
# CHANGE PASSWORD
# =========================
@router.post("/change-password")
def change_password(payload: ChangePasswordIn, db: Session = Depends(get_db), user=Depends(get_current_user)):
    me = _require_user(db, user)

    if not verify_password(payload.current_password, me.password_hash):
        raise HTTPException(status_code=400, detail="Contraseña actual incorrecta")

    if len(payload.new_password) < 8:
        raise HTTPException(status_code=400, detail="La nueva contraseña debe tener al menos 8 caracteres")

    me.password_hash = hash_password(payload.new_password)
    db.add(me)
    db.commit()
    return {"ok": True}


# =========================
# GET/CREATE PREFERENCES / PRIVACY
# =========================
def _get_or_create_prefs(db: Session, user_id: int) -> UserPreferences:
    prefs = db.query(UserPreferences).filter(UserPreferences.user_id == user_id).first()
    if not prefs:
        prefs = UserPreferences(user_id=user_id)
        db.add(prefs)
        db.commit()
        db.refresh(prefs)
    return prefs


def _get_or_create_privacy(db: Session, user_id: int) -> UserPrivacy:
    p = db.query(UserPrivacy).filter(UserPrivacy.user_id == user_id).first()
    if not p:
        p = UserPrivacy(user_id=user_id)
        db.add(p)
        db.commit()
        db.refresh(p)
    return p


# =========================
# PREFERENCES
# =========================
@router.get("/preferences", response_model=PreferencesOut)
def get_preferences(db: Session = Depends(get_db), user=Depends(get_current_user)):
    uid = _user_id(db, user)
    prefs = _get_or_create_prefs(db, uid)
    return PreferencesOut(
        email_notify_enabled=bool(prefs.email_notify_enabled),
        notify_status_changes=bool(prefs.notify_status_changes),
        notify_corrections=bool(prefs.notify_corrections),
        notify_approved_rejected=bool(prefs.notify_approved_rejected),
    )


@router.patch("/preferences", response_model=PreferencesOut)
def update_preferences(payload: PreferencesUpdate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    uid = _user_id(db, user)
    prefs = _get_or_create_prefs(db, uid)

    for k, v in payload.dict(exclude_unset=True).items():
        # IMPORTANTE: no ignorar False
        if v is not None:
            setattr(prefs, k, v)

    db.add(prefs)
    db.commit()
    db.refresh(prefs)

    return PreferencesOut(
        email_notify_enabled=bool(prefs.email_notify_enabled),
        notify_status_changes=bool(prefs.notify_status_changes),
        notify_corrections=bool(prefs.notify_corrections),
        notify_approved_rejected=bool(prefs.notify_approved_rejected),
    )


# =========================
# PRIVACY
# =========================
@router.get("/privacy", response_model=PrivacyOut)
def get_privacy(db: Session = Depends(get_db), user=Depends(get_current_user)):
    uid = _user_id(db, user)
    p = _get_or_create_privacy(db, uid)
    return PrivacyOut(show_name=bool(p.show_name), show_email=bool(p.show_email))


@router.patch("/privacy", response_model=PrivacyOut)
def update_privacy(payload: PrivacyUpdate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    uid = _user_id(db, user)
    p = _get_or_create_privacy(db, uid)

    for k, v in payload.dict(exclude_unset=True).items():
        # IMPORTANTE: no ignorar False
        if v is not None:
            setattr(p, k, v)

    db.add(p)
    db.commit()
    db.refresh(p)
    return PrivacyOut(show_name=bool(p.show_name), show_email=bool(p.show_email))
