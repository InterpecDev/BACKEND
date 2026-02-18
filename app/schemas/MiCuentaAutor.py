from pydantic import BaseModel, EmailStr, Field

class AutorMeOut(BaseModel):
    id: int
    name: str
    email: EmailStr
    role: str

    class Config:
        from_attributes = True

class AutorPreferencesIn(BaseModel):
    email_notify_enabled: bool = True
    notify_status_changes: bool = True
    notify_corrections: bool = True
    notify_approved_rejected: bool = True

class AutorPreferencesOut(AutorPreferencesIn):
    pass

class AutorPrivacyIn(BaseModel):
    show_name: bool = True
    show_email: bool = False

class AutorPrivacyOut(AutorPrivacyIn):
    pass

class AutorChangePasswordIn(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=8)
