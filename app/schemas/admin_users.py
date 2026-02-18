from pydantic import BaseModel, EmailStr
from typing import Optional, Literal, Union

Role = Literal["editorial", "dictaminador", "autor"]

class AdminUserOut(BaseModel):
    id: int
    name: str
    email: EmailStr
    role: Role
    institution: Optional[str] = None
    cvo_snii: Optional[str] = None
    active: Union[int, bool]
    created_at: str
    signature_url: Optional[str] = None

class AdminUserCreate(BaseModel):
    name: str
    email: EmailStr
    role: Role
    institution: Optional[str] = None
    cvo_snii: Optional[str] = None

class AdminUserPatch(BaseModel):
    active: Optional[int] = None
