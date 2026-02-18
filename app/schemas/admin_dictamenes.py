# app/schemas/admin_dictamenes.py
from pydantic import BaseModel
from typing import Literal, Optional

Decision = Literal["APROBADO", "CORRECCIONES", "RECHAZADO"]
DictamenStatus = Literal["BORRADOR", "GENERADO", "FIRMADO"]
DictamenTipo = Literal["INVESTIGACION", "DOCENCIA"]


class AdminDictamenRowOut(BaseModel):
    id: int
    folio: str

    capituloId: int
    capitulo: str
    libro: str
    evaluador: str

    decision: Decision
    promedio: float
    status: DictamenStatus
    updatedAt: str

    class Config:
        from_attributes = True


class DictamenStatusUpdateIn(BaseModel):
    status: DictamenStatus


class DictamenDecisionUpdateIn(BaseModel):
    decision: Decision
    promedio: Optional[float] = None
