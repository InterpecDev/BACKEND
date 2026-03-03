from pydantic import BaseModel
from typing import Optional, Literal
from datetime import datetime  # ✅ agrega esto


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

class DictChapterRowOut(BaseModel):
    id: int
    title: str
    status: ChapterStatus  # ← Ahora acepta todos
    updated_at: str

    book_name: Optional[str] = None
    author_name: Optional[str] = None
    author_email: Optional[str] = None
    # ✅ Archivo original
    file_path: Optional[str] = None

    # ✅ NUEVO: versión corregida reenviada por el autor
    corrected_file_path: Optional[str] = None
    corrected_updated_at: Optional[str] = None
    
    deadline_at: Optional[str] = None
    deadline_stage: Optional[str] = None
     # ✅ NUEVO: fecha límite que dictaminador asigna al autor
    author_deadline_at: Optional[str] = None
    
    class Config:
        from_attributes = True

class DictChapterStatusUpdateIn(BaseModel):
    status: ChapterStatus  # ← Ahora acepta todos
    comment: Optional[str] = None
    author_deadline_at: Optional[datetime] = None