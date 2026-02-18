# app/models/chapter_history.py
from sqlalchemy import Column, BigInteger, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.session import Base

class ChapterHistory(Base):
    __tablename__ = "chapter_history"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    chapter_id = Column(BigInteger, ForeignKey("chapters.id", ondelete="CASCADE"), nullable=False, index=True)

    by = Column(String(150), nullable=False)
    action = Column(String(150), nullable=False)
    detail = Column(Text, nullable=False)
    at = Column(DateTime, nullable=False, server_default=func.now())

    # ✅ RELACIÓN CON STRING
    chapter = relationship("Chapter", back_populates="history")