from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.core.deps import get_current_user
from app.core.security import verify_password, hash_password

from app.models.user import User
from app.models.MiCuentaAutorPreferences import MiCuentaAutorPreferences
from app.models.MiCuentaAutorPrivacy import MiCuentaAutorPrivacy

from app.schemas.MiCuentaAutor import (
    AutorMeOut,
    AutorPreferencesIn, AutorPreferencesOut,
    AutorPrivacyIn, AutorPrivacyOut,
    AutorChangePasswordIn
)

router = APIRouter(prefix="/account", tags=["autor:cuenta"])


def _prefs_out(p: MiCuentaAutorPreferences) -> AutorPreferencesOut:
    return AutorPreferencesOut(
        email_notify_enabled=bool(p.email_notify_enabled),
        notify_status_changes=bool(p.notify_status_changes),
        notify_corrections=bool(p.notify_corrections),
        notify_approved_rejected=bool(p.notify_approved_rejected),
    )

def _privacy_out(p: MiCuentaAutorPrivacy) -> AutorPrivacyOut:
    return AutorPrivacyOut(
        show_name=bool(p.show_name),
        show_email=bool(p.show_email),
    )


@router.get("/me", response_model=AutorMeOut)
def autor_me(current_user: User = Depends(get_current_user)):
    # Si quieres asegurar que solo autor use esto:
    # if current_user.role != "autor":
    #     raise HTTPException(status_code=403, detail="Solo autores.")
    return current_user


@router.get("/preferences", response_model=AutorPreferencesOut)
def autor_get_preferences(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = db.query(MiCuentaAutorPreferences)\
            .filter(MiCuentaAutorPreferences.user_id == current_user.id)\
            .first()

    if not row:
        row = MiCuentaAutorPreferences(user_id=current_user.id)
        db.add(row)
        db.commit()
        db.refresh(row)

    return _prefs_out(row)


@router.patch("/preferences", response_model=AutorPreferencesOut)
def autor_update_preferences(
    payload: AutorPreferencesIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = db.query(MiCuentaAutorPreferences)\
            .filter(MiCuentaAutorPreferences.user_id == current_user.id)\
            .first()

    if not row:
        row = MiCuentaAutorPreferences(user_id=current_user.id)
        db.add(row)

    row.email_notify_enabled = 1 if payload.email_notify_enabled else 0
    row.notify_status_changes = 1 if payload.notify_status_changes else 0
    row.notify_corrections = 1 if payload.notify_corrections else 0
    row.notify_approved_rejected = 1 if payload.notify_approved_rejected else 0

    db.commit()
    db.refresh(row)
    return _prefs_out(row)


@router.get("/privacy", response_model=AutorPrivacyOut)
def autor_get_privacy(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = db.query(MiCuentaAutorPrivacy)\
            .filter(MiCuentaAutorPrivacy.user_id == current_user.id)\
            .first()

    if not row:
        row = MiCuentaAutorPrivacy(user_id=current_user.id)
        db.add(row)
        db.commit()
        db.refresh(row)

    return _privacy_out(row)


@router.patch("/privacy", response_model=AutorPrivacyOut)
def autor_update_privacy(
    payload: AutorPrivacyIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = db.query(MiCuentaAutorPrivacy)\
            .filter(MiCuentaAutorPrivacy.user_id == current_user.id)\
            .first()

    if not row:
        row = MiCuentaAutorPrivacy(user_id=current_user.id)
        db.add(row)

    row.show_name = 1 if payload.show_name else 0
    row.show_email = 1 if payload.show_email else 0

    db.commit()
    db.refresh(row)
    return _privacy_out(row)


@router.post("/change-password")
def autor_change_password(
    payload: AutorChangePasswordIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not verify_password(payload.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Contraseña actual incorrecta.")

    current_user.password_hash = hash_password(payload.new_password)
    db.commit()
    return {"ok": True}
