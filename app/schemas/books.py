from pydantic import BaseModel
from datetime import datetime

class BookOut(BaseModel):
    id: int
    name: str
    year: int
    author_id: int
    created_at: datetime

    class Config:
        from_attributes = True

class BookCreate(BaseModel):
    name: str
    year: int
