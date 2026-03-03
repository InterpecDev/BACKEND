from pydantic import BaseModel
from typing import Optional, Literal

# Versión completa con TODOS los status (los viejos y los nuevos)
ChapterStatus = Literal[
    "RECIBIDO",
    "ASIGNADO_A_DICTAMINADOR",
    "ENVIADO_A_DICTAMINADOR",           # ← NUEVO
    "EN_REVISION_DICTAMINADOR",          # ← NUEVO
    "CORRECCIONES_SOLICITADAS_A_AUTOR",  # ← NUEVO
    "CORRECCIONES",                      # ← viejo
    "REENVIADO_POR_AUTOR",
    "REVISADO_POR_EDITORIAL",            # ← NUEVO
    "LISTO_PARA_FIRMA",                   # ← NUEVO
    "FIRMADO",                            # ← NUEVO
    "EN_REVISION",                        # ← viejo
    "APROBADO",
    "RECHAZADO",
]

class AdminChapterRowOut(BaseModel):
    id: int
    folio: Optional[str] = None
    title: str
    book_id: int
    book_name: str
    author_name: str
    author_email: str
    status: ChapterStatus  # ← Usa la versión completa
    updated_at: str
    evaluator_email: Optional[str] = None 
    deadline_at: Optional[str] = None
    deadline_stage: Optional[str] = None

    class Config:
        from_attributes = True

class ChapterStatusUpdateIn(BaseModel):
    status: ChapterStatus  # ← Usa la versión completa


class CorreccionIn(BaseModel):
    comment: str

class AdminChapterFolioUpdateIn(BaseModel):
    folio: str