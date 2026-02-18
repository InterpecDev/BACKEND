from sqlalchemy import Column, BigInteger, String, Enum, DateTime, SmallInteger
from sqlalchemy.sql import func
from app.db.session import Base
from sqlalchemy.orm import relationship


class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    name = Column(String(150), nullable=False)
    email = Column(String(150), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=False)

    role = Column(Enum("editorial", "dictaminador", "autor", name="role_enum"), nullable=False)

    institution = Column(String(200), nullable=True)
    cvo_snii = Column(String(100), nullable=True)

    active = Column(SmallInteger, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    
    
    # Dictámenes donde este usuario es evaluador/dictaminador
    dictamenes = relationship("Dictamen", back_populates="evaluador")