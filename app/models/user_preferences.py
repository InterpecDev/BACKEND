from datetime import datetime
from sqlalchemy import Column, BigInteger, DateTime, Boolean, ForeignKey
from app.db.session import Base

class UserPreferences(Base):
    __tablename__ = "user_preferences"

    user_id = Column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
        index=True
    )

    email_notify_enabled = Column(Boolean, nullable=False, default=True)
    notify_status_changes = Column(Boolean, nullable=False, default=True)
    notify_corrections = Column(Boolean, nullable=False, default=True)
    notify_approved_rejected = Column(Boolean, nullable=False, default=True)

    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
