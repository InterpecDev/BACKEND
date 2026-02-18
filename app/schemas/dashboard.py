from pydantic import BaseModel
from typing import List

class DashboardSummaryOut(BaseModel):
    capitulos_recibidos_hoy: int
    en_revision: int
    correcciones: int
    aprobados: int
    constancias_pendientes: int

class PendingItem(BaseModel):
    folio: str
    capitulo: str
    libro: str
    estado: str

class DashboardPendingOut(BaseModel):
    items: List[PendingItem]
