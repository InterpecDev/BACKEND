from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.db.session import get_db
from app.core.deps import get_current_user
from app.schemas.dashboard import DashboardSummaryOut, DashboardPendingOut

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummaryOut)
def dashboard_summary(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),  # payload JWT
):
    user_id = int(user.get("sub"))
    role = user.get("role")

    if role == "dictaminador":
        # Solo lo del evaluador actual
        q = text("""
            SELECT
              SUM(CASE WHEN c.status = 'RECIBIDO' AND DATE(c.updated_at) = CURDATE() THEN 1 ELSE 0 END) AS capitulos_recibidos_hoy,
              SUM(CASE WHEN c.status = 'EN_REVISION' THEN 1 ELSE 0 END) AS en_revision,
              SUM(CASE WHEN c.status = 'CORRECCIONES' THEN 1 ELSE 0 END) AS correcciones,
              SUM(CASE WHEN c.status = 'APROBADO' THEN 1 ELSE 0 END) AS aprobados,
              SUM(CASE WHEN d.decision = 'APROBADO' AND (d.status IS NULL OR d.status <> 'FIRMADO') THEN 1 ELSE 0 END) AS constancias_pendientes
            FROM dictamenes d
            JOIN chapters c ON c.id = d.chapter_id
            WHERE d.evaluador_id = :uid
        """)
        row = db.execute(q, {"uid": user_id}).mappings().first() or {}

    else:
        # Editorial ve todo
        q = text("""
            SELECT
              SUM(CASE WHEN c.status = 'RECIBIDO' AND DATE(c.updated_at) = CURDATE() THEN 1 ELSE 0 END) AS capitulos_recibidos_hoy,
              SUM(CASE WHEN c.status = 'EN_REVISION' THEN 1 ELSE 0 END) AS en_revision,
              SUM(CASE WHEN c.status = 'CORRECCIONES' THEN 1 ELSE 0 END) AS correcciones,
              SUM(CASE WHEN c.status = 'APROBADO' THEN 1 ELSE 0 END) AS aprobados,
              (
                SELECT COUNT(*)
                FROM dictamenes d
                WHERE d.decision = 'APROBADO'
                  AND (d.status IS NULL OR d.status <> 'FIRMADO')
              ) AS constancias_pendientes
            FROM chapters c
        """)
        row = db.execute(q).mappings().first() or {}

    return {
        "capitulos_recibidos_hoy": int(row.get("capitulos_recibidos_hoy") or 0),
        "en_revision": int(row.get("en_revision") or 0),
        "correcciones": int(row.get("correcciones") or 0),
        "aprobados": int(row.get("aprobados") or 0),
        "constancias_pendientes": int(row.get("constancias_pendientes") or 0),
    }


@router.get("/pending", response_model=DashboardPendingOut)
def dashboard_pending(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    user_id = int(user.get("sub"))
    role = user.get("role")

    # Si dictaminador: solo sus dictámenes (y pendientes)
    if role == "dictaminador":
        q = text("""
            SELECT
              d.folio AS folio,
              c.title AS capitulo,
              b.name AS libro,
              CASE
                WHEN d.decision = 'CORRECCIONES' THEN 'Correcciones'
                WHEN d.decision = 'RECHAZADO' THEN 'Rechazado'
                WHEN d.decision = 'APROBADO' THEN 'Aprobado'
                ELSE c.status
              END AS estado
            FROM dictamenes d
            JOIN chapters c ON c.id = d.chapter_id
            JOIN books b ON b.id = c.book_id
            WHERE d.evaluador_id = :uid
              AND (
                (d.status <> 'FIRMADO' OR d.status IS NULL)
                OR (d.decision = 'CORRECCIONES')
                OR (c.status IN ('EN_REVISION','CORRECCIONES'))
              )
            ORDER BY d.created_at DESC
            LIMIT 10
        """)
        rows = db.execute(q, {"uid": user_id}).mappings().all() or []

    else:
        # Editorial: todos
        q = text("""
            SELECT
              d.folio AS folio,
              c.title AS capitulo,
              b.name AS libro,
              CASE
                WHEN d.decision = 'CORRECCIONES' THEN 'Correcciones'
                WHEN d.decision = 'RECHAZADO' THEN 'Rechazado'
                WHEN d.decision = 'APROBADO' THEN 'Aprobado'
                ELSE c.status
              END AS estado
            FROM dictamenes d
            JOIN chapters c ON c.id = d.chapter_id
            JOIN books b ON b.id = c.book_id
            WHERE
              (d.status <> 'FIRMADO' OR d.status IS NULL)
              OR (d.decision = 'CORRECCIONES')
              OR (c.status IN ('EN_REVISION','CORRECCIONES'))
            ORDER BY d.created_at DESC
            LIMIT 10
        """)
        rows = db.execute(q).mappings().all() or []

    items = []
    for r in rows:
        items.append({
            "folio": str(r.get("folio") or ""),
            "capitulo": str(r.get("capitulo") or "—"),
            "libro": str(r.get("libro") or "—"),
            "estado": str(r.get("estado") or "—"),
        })

    return {"items": items}
