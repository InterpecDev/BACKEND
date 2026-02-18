import os
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.db.session import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.models.book import Book
from app.models.chapter import Chapter
from app.models.dictamen import Dictamen
from app.models.chapter_version import ChapterVersion
from app.models.chapter_history import ChapterHistory

router = APIRouter(prefix="/chapters", tags=["chapters"])

STORAGE_DIR = os.getenv("STORAGE_DIR", "storage")
CHAPTERS_DIR = os.path.join(STORAGE_DIR, "chapters")
os.makedirs(CHAPTERS_DIR, exist_ok=True)

def require_editorial(user: User):
    if user.role != "editorial":
        raise HTTPException(status_code=403, detail="Solo editorial puede realizar esta acción.")

def push_history(db: Session, chapter_id: int, by: str, action: str, detail: str):
    h = ChapterHistory(chapter_id=chapter_id, by=by, action=action, detail=detail)
    db.add(h)
    db.flush()
    return h


@router.get("/{chapter_id}")
def chapter_detail(chapter_id: int, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    # editorial / dictaminador pueden ver
    if me.role not in ("editorial", "dictaminador"):
        raise HTTPException(status_code=403, detail="No autorizado.")

    ch = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    if not ch:
        raise HTTPException(status_code=404, detail="Capítulo no encontrado.")

    book = db.query(Book).filter(Book.id == ch.book_id).first()

    versions = (
        db.query(ChapterVersion)
        .filter(ChapterVersion.chapter_id == ch.id)
        .order_by(desc(ChapterVersion.uploaded_at))
        .all()
    )

    # fallback: si aún no hay versiones en tabla, usa file_path actual como “v1”
    if not versions and ch.file_path:
        versions_payload = [{
            "id": "0",
            "versionLabel": "v1",
            "fileName": os.path.basename(ch.file_path),
            "uploadedAt": ch.updated_at.isoformat() if ch.updated_at else "",
            "note": "Archivo inicial",
        }]
    else:
        versions_payload = [{
            "id": str(v.id),
            "versionLabel": v.version_label,
            "fileName": v.file_name,
            "uploadedAt": v.uploaded_at.isoformat(),
            "note": v.note or "",
        } for v in versions]

    dictamenes = (
        db.query(Dictamen)
        .filter(Dictamen.chapter_id == ch.id)
        .order_by(desc(Dictamen.created_at))
        .all()
    )

    dictamenes_payload = []
    for d in dictamenes:
        evaluator = db.query(User).filter(User.id == d.evaluador_id).first()
        dictamenes_payload.append({
            "id": str(d.id),
            "evaluator": evaluator.name if evaluator else "Dictaminador",
            "type": d.tipo,  # INVESTIGACION / DOCENCIA
            "scoreAvg": float(d.promedio or 0.0),
            "decision": d.decision,  # APROBADO/CORRECCIONES/RECHAZADO
            "createdAt": d.created_at.isoformat(),
            "firmado": True if d.status == "FIRMADO" else False,
        })

    history = (
        db.query(ChapterHistory)
        .filter(ChapterHistory.chapter_id == ch.id)
        .order_by(desc(ChapterHistory.at))
        .all()
    )

    history_payload = [{
        "id": str(h.id),
        "at": h.at.isoformat(),
        "by": h.by,
        "action": h.action,
        "detail": h.detail,
    } for h in history]

    return {
        "id": str(ch.id),
        "folio": getattr(ch, "folio", f"CH-{ch.id}"),  # por si no tienes folio en tu modelo real
        "title": ch.title,
        "book": book.name if book else f"Book {ch.book_id}",
        "author": ch.author_name,
        "authorEmail": ch.author_email,
        "status": ch.status,

        # dictaminador asignado (persistente si agregaste columnas)
        "evaluatorName": ch.evaluator_name,
        "evaluatorEmail": ch.evaluator_email,

        "versions": versions_payload,
        "dictamenes": dictamenes_payload,
        "history": history_payload,
    }


@router.post("/{chapter_id}/assign-evaluator")
def assign_evaluator(
    chapter_id: int,
    evaluator_name: str = Form(...),
    evaluator_email: str = Form(...),
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    require_editorial(me)

    ch = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    if not ch:
        raise HTTPException(status_code=404, detail="Capítulo no encontrado.")

    u = db.query(User).filter(User.email == evaluator_email).first()
    if not u or u.role != "dictaminador":
        raise HTTPException(status_code=400, detail="El correo no corresponde a un dictaminador registrado.")

    # guardar asignación (requiere columnas nuevas)
    ch.evaluator_id = u.id
    ch.evaluator_name = u.name  # fuerza que coincida con users
    ch.evaluator_email = u.email
    ch.status = "ASIGNADO_A_DICTAMINADOR"

    push_history(db, ch.id, "Editorial", "Asignación", f"Se asignó dictaminador: {u.name} ({u.email})")

    db.add(ch)
    db.commit()
    return {"ok": True}


@router.patch("/{chapter_id}/status")
def set_status(
    chapter_id: int,
    status: str = Form(...),
    reason: str = Form(""),
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    # editorial decide status
    require_editorial(me)

    ch = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    if not ch:
        raise HTTPException(status_code=404, detail="Capítulo no encontrado.")

    # OJO: tu enum actual solo soporta 7 estados.
    # Aquí solo aceptamos esos para no romper DB.
    allowed = {"RECIBIDO","ASIGNADO_A_DICTAMINADOR","EN_REVISION","CORRECCIONES","REENVIADO_POR_AUTOR","APROBADO","RECHAZADO"}
    if status not in allowed:
        raise HTTPException(status_code=400, detail=f"Estado no permitido por tu BD actual: {status}")

    ch.status = status
    push_history(db, ch.id, "Editorial", "Cambio de estado", status + (f" — {reason}" if reason else ""))
    db.add(ch)
    db.commit()
    return {"ok": True}


@router.post("/{chapter_id}/versions")
def upload_new_version(
    chapter_id: int,
    file: UploadFile = File(...),
    note: str = Form(""),
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    # editorial o autor pueden subir (ajusta si quieres)
    if me.role not in ("editorial", "autor"):
        raise HTTPException(status_code=403, detail="No autorizado.")

    ch = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    if not ch:
        raise HTTPException(status_code=404, detail="Capítulo no encontrado.")

    safe_name = file.filename.replace(" ", "_").replace("/", "_").replace("\\", "_")
    out_name = f"{chapter_id}_{int(datetime.now().timestamp())}_{safe_name}"
    out_path = os.path.join(CHAPTERS_DIR, out_name)

    with open(out_path, "wb") as f:
        f.write(file.file.read())

    # calcular siguiente versión
    last = (
        db.query(ChapterVersion)
        .filter(ChapterVersion.chapter_id == chapter_id)
        .order_by(desc(ChapterVersion.uploaded_at))
        .first()
    )
    next_num = 1
    if last and last.version_label.startswith("v"):
        try:
            next_num = int(last.version_label.replace("v","")) + 1
        except:
            next_num = 1

    v = ChapterVersion(
        chapter_id=chapter_id,
        version_label=f"v{next_num}",
        file_name=safe_name,
        file_path=out_path,
        note=note or None,
    )
    db.add(v)

    # opcional: actualizar file_path “actual”
    ch.file_path = out_path
    db.add(ch)

    push_history(db, ch.id, me.role.capitalize(), "Nueva versión", f"Se subió {v.version_label}: {safe_name}")
    db.commit()
    return {"ok": True, "versionLabel": v.version_label}


@router.get("/{chapter_id}/versions/{version_id}/download")
def download_version(chapter_id: int, version_id: int, db: Session = Depends(get_db), me: User = Depends(get_current_user)):
    if me.role not in ("editorial", "dictaminador", "autor"):
        raise HTTPException(status_code=403, detail="No autorizado.")

    if str(version_id) == "0":
        # fallback: usar el file_path principal
        ch = db.query(Chapter).filter(Chapter.id == chapter_id).first()
        if not ch or not ch.file_path:
            raise HTTPException(status_code=404, detail="Archivo no encontrado.")
        return FileResponse(ch.file_path, filename=os.path.basename(ch.file_path), media_type="application/octet-stream")

    v = db.query(ChapterVersion).filter(ChapterVersion.id == int(version_id), ChapterVersion.chapter_id == chapter_id).first()
    if not v or not os.path.exists(v.file_path):
        raise HTTPException(status_code=404, detail="Versión no encontrada.")
    return FileResponse(v.file_path, filename=v.file_name, media_type="application/octet-stream")


@router.post("/{chapter_id}/history/comment")
def add_comment(
    chapter_id: int,
    detail: str = Form(...),
    db: Session = Depends(get_db),
    me: User = Depends(get_current_user),
):
    if me.role not in ("editorial", "dictaminador"):
        raise HTTPException(status_code=403, detail="No autorizado.")

    ch = db.query(Chapter).filter(Chapter.id == chapter_id).first()
    if not ch:
        raise HTTPException(status_code=404, detail="Capítulo no encontrado.")

    push_history(db, ch.id, me.role.capitalize(), "Comentario", detail)
    db.commit()
    return {"ok": True}






