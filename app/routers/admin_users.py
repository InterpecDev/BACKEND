import os
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.models.user_signature import UserSignature
from app.core.security import hash_password
from app.core.deps import get_current_user

from app.schemas.admin_users import AdminUserOut, AdminUserCreate, AdminUserPatch

router = APIRouter(prefix="/admin/users", tags=["admin-users"])

SIGN_DIR = os.path.join("storage", "signatures")
os.makedirs(SIGN_DIR, exist_ok=True)

ALLOWED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/jpg"}


def require_admin(payload: dict):
    if payload.get("role") != "editorial":
        raise HTTPException(status_code=403, detail="Solo editorial/admin puede realizar esta acción.")


def public_url(path: str) -> str:
    rel = path.replace("\\", "/")
    if rel.startswith("storage/"):
        rel = rel[len("storage/"):]
    return f"/api/storage/{rel}"


def get_active_sig(db: Session, user_id: int) -> Optional[UserSignature]:
    return db.query(UserSignature).filter(UserSignature.user_id == user_id, UserSignature.active == 1).first()


def to_out(db: Session, u: User) -> AdminUserOut:
    sig = get_active_sig(db, int(u.id))
    return AdminUserOut(
        id=int(u.id),
        name=u.name,
        email=u.email,
        role=u.role,
        institution=u.institution,
        cvo_snii=u.cvo_snii,
        active=int(u.active or 0),
        created_at=u.created_at.isoformat() if u.created_at else "",
        signature_url=(sig.image_url if sig else None),
    )


@router.get("", response_model=List[AdminUserOut])
def list_users(
    role: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    payload: dict = Depends(get_current_user),
):
    require_admin(payload)

    q = db.query(User)
    if role:
        q = q.filter(User.role == role)

    items = q.order_by(User.created_at.desc()).all()
    return [to_out(db, u) for u in items]


@router.post("", response_model=AdminUserOut)
def create_user(
    body: AdminUserCreate,
    db: Session = Depends(get_db),
    payload: dict = Depends(get_current_user),
):
    require_admin(payload)

    email = body.email.strip().lower()

    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="Ese correo ya existe.")

    role = body.role

    if role not in ("dictaminador", "autor"):
        raise HTTPException(status_code=400, detail="Solo puedes crear dictaminador o autor.")

    # ✅ regla de contraseñas según tu requerimiento:
    if role == "dictaminador":
        if not body.cvo_snii or not body.cvo_snii.strip():
            raise HTTPException(status_code=422, detail="Para dictaminador, CVU es obligatorio.")
        raw_password = body.cvo_snii.strip()  # tú decides si aquí limpias "CVU: "
    else:  # autor
        raw_password = body.name.strip()  # contraseña = nombre

    u = User(
        name=body.name.strip(),
        email=email,
        password_hash=hash_password(raw_password),
        role=role,
        institution=(body.institution.strip() if body.institution else None),
        cvo_snii=(body.cvo_snii.strip() if body.cvo_snii else None),
        active=1,
    )

    db.add(u)
    db.commit()
    db.refresh(u)

    return to_out(db, u)


@router.patch("/{user_id}", response_model=AdminUserOut)
def patch_user(
    user_id: int,
    body: AdminUserPatch,
    db: Session = Depends(get_db),
    payload: dict = Depends(get_current_user),
):
    require_admin(payload)

    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")

    if body.active is not None:
        if body.active not in (0, 1):
            raise HTTPException(status_code=422, detail="active debe ser 0 o 1.")
        u.active = body.active

    db.commit()
    db.refresh(u)
    return to_out(db, u)


@router.get("/{user_id}/signature")
def get_signature(
    user_id: int,
    db: Session = Depends(get_db),
    payload: dict = Depends(get_current_user),
):
    require_admin(payload)

    sig = get_active_sig(db, user_id)
    return {"signature_url": (sig.image_url if sig else None)}


@router.post("/{user_id}/signature")
async def upload_signature(
    user_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    payload: dict = Depends(get_current_user),
):
    require_admin(payload)

    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")

    if u.role != "dictaminador":
        raise HTTPException(status_code=400, detail="Solo dictaminadores pueden tener firma.")

    if file.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=415, detail="Formato inválido. Sube PNG o JPG.")

    ext = ".png" if file.content_type == "image/png" else ".jpg"
    filename = f"u_{u.id}{ext}"
    save_path = os.path.join(SIGN_DIR, filename)

    content = await file.read()
    if not content or len(content) < 50:
        raise HTTPException(status_code=400, detail="Archivo vacío o inválido.")

    with open(save_path, "wb") as f:
        f.write(content)

    url = public_url(save_path)

    prev = get_active_sig(db, user_id)
    if prev:
        prev.active = 0

    sig = UserSignature(
        user_id=user_id,
        image_url=url,
        image_mime=file.content_type,
        active=1,
    )
    db.add(sig)
    db.commit()

    return {"signature_url": url}



@router.delete("/{user_id}", status_code=204)
def delete_user(
    user_id: int,
    db: Session = Depends(get_db),
    payload: dict = Depends(get_current_user),
):
    require_admin(payload)

    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")

    # Seguridad: no permitir eliminar editorial/admin
    if u.role == "editorial":
        raise HTTPException(status_code=400, detail="No puedes eliminar usuarios editoriales/admin.")

    # --- borrar firma física (si existe) ---
    # En tu BD guardas image_url como "/api/storage/...."
    sigs = db.query(UserSignature).filter(UserSignature.user_id == user_id).all()
    for s in sigs:
        try:
            url = (s.image_url or "").replace("\\", "/")
            # url ejemplo: "/api/storage/signatures/u_2.png"
            if url.startswith("/api/storage/"):
                rel = url[len("/api/storage/"):]  # "signatures/u_2.png"
                path = os.path.join("storage", rel.replace("/", os.sep))  # "storage/signatures/u_2.png"
                if os.path.exists(path):
                    os.remove(path)
        except Exception:
            # No bloquea el borrado por un error de filesystem
            pass

    # --- borrar usuario (FK cascades harán el resto) ---
    db.delete(u)
    db.commit()
    return
