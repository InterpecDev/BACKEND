from sqlalchemy import (
    Column,
    BigInteger,
    String,
    Enum,
    DECIMAL,
    Text,
    DateTime,
    ForeignKey,
    Index,
    Integer,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.mysql import JSON

from app.db.session import Base

DICTAMEN_TIPOS = ("INVESTIGACION", "DOCENCIA")
DICTAMEN_DECISIONS = ("APROBADO", "CORRECCIONES", "RECHAZADO")
DICTAMEN_STATUS = ("BORRADOR", "GENERADO", "FIRMADO")


class Dictamen(Base):
    __tablename__ = "dictamenes"

    id = Column(BigInteger, primary_key=True, autoincrement=True, index=True)
    folio = Column(String(50), nullable=False, unique=True, index=True)

    chapter_id = Column(Integer, ForeignKey("chapters.id"), nullable=False, index=True)
    evaluador_id = Column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)

    tipo = Column(String(80), nullable=False)

    decision = Column(Enum(*DICTAMEN_DECISIONS, name="dictamen_decision"), nullable=False)
    status = Column(
        Enum(*DICTAMEN_STATUS, name="dictamen_status"),
        nullable=False,
        server_default="BORRADOR",
    )

    promedio = Column(DECIMAL(3, 1), nullable=True)
    comentarios = Column(Text, nullable=True)
    conflicto_interes = Column(Text, nullable=True)

    template_docx_path = Column(String(500), nullable=True)
    recipient_name = Column(String(180), nullable=True)
    constancia_data_json = Column(JSON, nullable=True)
    generated_docx_path = Column(String(500), nullable=True)

    pdf_path = Column(String(500), nullable=True)
    signed_pdf_path = Column(String(500), nullable=True)
    signed_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=True, onupdate=func.now())

    chapter = relationship("Chapter", back_populates="dictamenes")
    evaluador = relationship("User")

    criterios = relationship(
        "DictamenCriterio",
        back_populates="dictamen",
        cascade="all, delete-orphan",
        order_by="DictamenCriterio.id.asc()",
    )

    __table_args__ = (
        Index("idx_dictamen_chapter", "chapter_id"),
        Index("idx_dictamen_evaluador", "evaluador_id"),
    )