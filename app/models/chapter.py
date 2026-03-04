# app/models/chapter.py
from datetime import datetime
from sqlalchemy import Column, BigInteger, String, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship
from app.db.session import Base

CHAPTER_STATUSES = (
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
)

class Chapter(Base):
    __tablename__ = "chapters"

    id = Column(BigInteger, primary_key=True, index=True)

    book_id = Column(BigInteger, ForeignKey("books.id", ondelete="CASCADE"), nullable=False, index=True)
    author_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    author_name = Column(String(255), nullable=False)
    author_email = Column(String(255), nullable=False)

    title = Column(String(255), nullable=False)

    status = Column(Enum(*CHAPTER_STATUSES, name="chapter_status"), nullable=False, default="RECIBIDO")

    file_path = Column(String(500), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    corrected_file_path = Column(String(500), nullable=True)
    corrected_updated_at = Column(DateTime, nullable=True)

    evaluator_id = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    evaluator_name = Column(String(255), nullable=True)
    evaluator_email = Column(String(255), nullable=True)

    # =========================
    # DEADLINES: Editorial -> Dictaminador
    # =========================
    deadline_stage = Column(String(50), nullable=True)
    deadline_at = Column(DateTime, nullable=True)
    deadline_set_at = Column(DateTime, nullable=True)
    deadline_set_by = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    deadline_setter = relationship("User", foreign_keys=[deadline_set_by])

    # =========================
    # DEADLINE: Dictaminador -> Autor (Correcciones)
    # =========================
    author_deadline_at = Column(DateTime, nullable=True)
    author_deadline_set_at = Column(DateTime, nullable=True)
    author_deadline_set_by = Column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    author_deadline_setter = relationship("User", foreign_keys=[author_deadline_set_by])

    folio = Column(String(50), nullable=True, unique=True, index=True)

    book = relationship("Book", back_populates="chapters")

    dictamenes = relationship("Dictamen", back_populates="chapter", cascade="all, delete-orphan")

    versions = relationship(
        "ChapterVersion",
        back_populates="chapter",
        cascade="all, delete-orphan",
        order_by="ChapterVersion.uploaded_at.desc()",
    )

    history = relationship(
        "ChapterHistory",
        back_populates="chapter",
        cascade="all, delete-orphan",
        order_by="ChapterHistory.at.desc()",
    )

    deadlines = relationship(
        "ChapterDeadline",
        back_populates="chapter",
        cascade="all, delete-orphan",
        order_by="ChapterDeadline.created_at.desc()",
    )