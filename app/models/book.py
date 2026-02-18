from datetime import datetime
from sqlalchemy import Column, BigInteger, String, DateTime, ForeignKey, Integer
from sqlalchemy.orm import relationship
from app.db.session import Base

class Book(Base):
    __tablename__ = "books"

    id = Column(BigInteger, primary_key=True, index=True)
    author_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    name = Column(String(255), nullable=False)
    year = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    chapters = relationship("Chapter", back_populates="book", cascade="all, delete-orphan")