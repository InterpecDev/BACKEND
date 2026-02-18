from pydantic import BaseModel, EmailStr
from typing import List

# Lo que espera tu frontend:
# AdminBookApi.author = { id, name, email }
class AdminAuthorOut(BaseModel):
    id: int
    name: str
    email: EmailStr

class AdminBookOut(BaseModel):
    id: int
    name: str
    year: int
    created_at: str

    author: AdminAuthorOut

    total_chapters: int
    approved: int
    corrections: int

class AdminChapterOut(BaseModel):
    id: int
    title: str
    author_name: str
    author_email: EmailStr
    status: str
    updated_at: str
