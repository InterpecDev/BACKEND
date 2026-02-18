from pydantic import BaseModel, EmailStr
from app.schemas.user import UserOut

class LoginIn(BaseModel):
    email: EmailStr
    password: str

class LoginOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut
