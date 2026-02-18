from datetime import datetime
from sqlalchemy import Column, BigInteger, DateTime, Boolean, ForeignKey
from app.db.session import Base

class UserPrivacy(Base):
    __tablename__ = "user_privacy"

    user_id = Column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
        index=True
    )

    show_name = Column(Boolean, nullable=False, default=True)
    show_email = Column(Boolean, nullable=False, default=False)

    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
