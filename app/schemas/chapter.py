# app/schemas/chapter.py

from pydantic import BaseModel
from typing import Optional, Literal
from datetime import datetime

# ✅ Versión extendida con TODOS los status
ChapterStatus = Literal[
    "RECIBIDO",
    "ASIGNADO_A_DICTAMINADOR",
    "ENVIADO_A_DICTAMINADOR",
    "EN_REVISION_DICTAMINADOR",
    "CORRECCIONES_SOLICITADAS_A_AUTOR",
    "CORRECCIONES",
    "REENVIADO_POR_AUTOR",
    "REVISADO_POR_EDITORIAL",
    "LISTO_PARA_FIRMA",
    "FIRMADO",
    "EN_REVISION",
    "APROBADO",
    "RECHAZADO",
]

class ChapterOut(BaseModel):
    id: int
    book_id: int
    author_id: int
    title: str
    status: ChapterStatus

    # ✅ archivo + fechas
    file_path: Optional[str] = None
    updated_at: Optional[datetime] = None

    # ✅ si tu modelo ya maneja correcciones
    corrected_file_path: Optional[str] = None
    corrected_updated_at: Optional[datetime] = None

    # ==========================================================
    # ✅ DEADLINE Editorial -> Dictaminador (si lo usas)
    # ==========================================================
    deadline_stage: Optional[str] = None
    deadline_at: Optional[datetime] = None
    deadline_set_at: Optional[datetime] = None
    deadline_set_by: Optional[int] = None

    # ==========================================================
    # ✅ DEADLINE Dictaminador -> Autor (ESTO ES LO IMPORTANTE)
    # ==========================================================
    author_deadline_at: Optional[datetime] = None
    author_deadline_set_at: Optional[datetime] = None
    author_deadline_set_by: Optional[int] = None

    class Config:
        from_attributes = True