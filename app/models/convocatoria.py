from sqlalchemy import Column, BigInteger, Integer, String, Text, Date, DateTime
from sqlalchemy.sql import func
from app.db.session import Base


class Convocatoria(Base):
    __tablename__ = "convocatorias"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    year = Column(Integer, nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    text = Column(Text, nullable=True)

    pdf_path = Column(String(500), nullable=True)          # ✅ debe ser NULL en tabla
    final_pdf_path = Column(String(500), nullable=True)  
    # ✅ si agregaste columna

    active = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, nullable=True)
