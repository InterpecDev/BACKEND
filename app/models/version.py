from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Text
from sqlalchemy.sql import func
from app.db.session import Base

class Version(Base):
    __tablename__ = "versions"
    
    id = Column(Integer, primary_key=True, index=True)
    chapter_id = Column(Integer, ForeignKey("chapters.id"), nullable=False)
    version_label = Column(String(50), nullable=False)
    file_name = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    note = Column(Text, nullable=True)
    uploaded_by = Column(String(50), nullable=False)  # autor, dictaminador, editorial
    created_at = Column(DateTime(timezone=True), server_default=func.now())