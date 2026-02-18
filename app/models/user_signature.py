from sqlalchemy import Column, BigInteger, String, DateTime, SmallInteger, ForeignKey, UniqueConstraint, Index
from sqlalchemy.sql import func
from app.db.session import Base

class UserSignature(Base):
    __tablename__ = "user_signatures"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    image_url = Column(String(500), nullable=False)
    image_mime = Column(String(80), nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    active = Column(SmallInteger, nullable=False, default=1)

    __table_args__ = (
        UniqueConstraint("user_id", "active", name="uq_signature_user_active"),
        Index("idx_signature_user_active", "user_id", "active"),
    )
