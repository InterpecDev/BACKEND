# app/models/chapter_version.py
from sqlalchemy import Column, BigInteger, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.session import Base

class ChapterVersion(Base):
    __tablename__ = "chapter_versions"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    chapter_id = Column(BigInteger, ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False, index=True)

    version_label = Column(String(20), nullable=False)
    file_name = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    note = Column(Text, nullable=True)
    uploaded_at = Column(DateTime, nullable=False, server_default=func.now())

    # ✅ RELACIÓN CON STRING
    chapter = relationship("Chapter", back_populates="versions")