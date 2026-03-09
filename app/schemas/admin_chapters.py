from pydantic import BaseModel, Field, conint
from typing import Optional, Literal, List

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

DecisionType = Literal["APROBADO", "CORRECCIONES", "RECHAZADO"]


class AdminChapterRowOut(BaseModel):
    id: int
    folio: Optional[str] = None
    title: str
    book_id: int
    book_name: str
    author_name: str
    author_email: str
    status: ChapterStatus
    updated_at: str
    evaluator_email: Optional[str] = None
    deadline_at: Optional[str] = None
    deadline_stage: Optional[str] = None

    class Config:
        from_attributes = True


class ChapterStatusUpdateIn(BaseModel):
    status: ChapterStatus


class CorreccionIn(BaseModel):
    comment: str


class AdminChapterFolioUpdateIn(BaseModel):
    folio: str


# =========================
# ✅ SCHEMAS EVALUACION
# =========================
class EvaluacionCriterioIn(BaseModel):
    id: str
    nombre: str
    puntaje: conint(ge=1, le=5)


class EvaluacionUpsertIn(BaseModel):
    chapter_id: int
    tipo: str = Field(..., min_length=1, max_length=80)
    criterios: List[EvaluacionCriterioIn]
    promedio: float
    decision: DecisionType
    comentarios: Optional[str] = None
    conflictos_interes: Optional[str] = None