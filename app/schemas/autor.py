from typing import Optional, List, Literal
from pydantic import BaseModel

ChapterStatus = Literal[
    "RECIBIDO",
    "ASIGNADO_A_DICTAMINADOR",
    "EN_REVISION",
    "CORRECCIONES",
    "REENVIADO_POR_AUTOR",
    "APROBADO",
    "RECHAZADO",
]

class ChapterOut(BaseModel):
    id: int
    title: str
    status: ChapterStatus
    updated_at: str
    file_path: Optional[str] = None

    class Config:
        from_attributes = True


class BookOut(BaseModel):
    id: int
    name: str
    year: int
    created_at: str

    class Config:
        from_attributes = True


class BookCreate(BaseModel):
    name: str
    year: int
