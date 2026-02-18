from pydantic import BaseModel, EmailStr
from typing import Optional

class AccountMeOut(BaseModel):
    id: int
    name: str
    email: EmailStr
    role: str

    class Config:
        from_attributes = True

class AccountMeUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None  # si NO quieres permitir cambiar correo, quítalo.

class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str

class PreferencesOut(BaseModel):
    email_notify_enabled: bool
    notify_status_changes: bool
    notify_corrections: bool
    notify_approved_rejected: bool

class PreferencesUpdate(BaseModel):
    email_notify_enabled: Optional[bool] = None
    notify_status_changes: Optional[bool] = None
    notify_corrections: Optional[bool] = None
    notify_approved_rejected: Optional[bool] = None

class PrivacyOut(BaseModel):
    show_name: bool
    show_email: bool

class PrivacyUpdate(BaseModel):
    show_name: Optional[bool] = None
    show_email: Optional[bool] = None
