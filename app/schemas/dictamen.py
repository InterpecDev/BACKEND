# app/schemas/dictamen.py
from datetime import datetime
from pydantic import BaseModel
from typing import Optional, Literal

DictamenStatus = Literal["BORRADOR", "GENERADO", "FIRMADO"]
DictamenDecision = Literal["APROBADO", "CORRECCIONES", "RECHAZADO"]
DictamenTipo = Literal["INVESTIGACION", "DOCENCIA"]

class DictamenOut(BaseModel):
    id: int
    folio: str
    chapter_id: int
    evaluador_id: int
    tipo: DictamenTipo
    decision: DictamenDecision
    status: DictamenStatus
    promedio: Optional[float] = None
    comentarios: Optional[str] = None
    conflicto_interes: Optional[str] = None
    pdf_path: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
