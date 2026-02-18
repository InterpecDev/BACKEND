from pydantic import BaseModel
from datetime import datetime
from typing import Optional, Literal

# ✅ Versión extendida con TODOS los status
ChapterStatus = Literal[
    "RECIBIDO",
    "ASIGNADO_A_DICTAMINADOR",
    "ENVIADO_A_DICTAMINADOR",           # ← NUEVO
    "EN_REVISION_DICTAMINADOR",          # ← NUEVO
    "CORRECCIONES_SOLICITADAS_A_AUTOR",  # ← NUEVO
    "CORRECCIONES",
    "REENVIADO_POR_AUTOR",
    "REVISADO_POR_EDITORIAL",            # ← NUEVO
    "LISTO_PARA_FIRMA",                  # ← NUEVO
    "FIRMADO",                           # ← NUEVO
    "EN_REVISION",
    "APROBADO",
    "RECHAZADO",
]

class ChapterOut(BaseModel):
    id: int
    book_id: int
    author_id: int
    title: str
    status: ChapterStatus  # ← Ahora acepta todos
    updated_at: datetime
    file_path: Optional[str] = None

    class Config:
        from_attributes = True