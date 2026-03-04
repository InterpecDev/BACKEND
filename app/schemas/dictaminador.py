# app/schemas/dictaminador.py
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class DictaminadorChapterOut(BaseModel):
    id: int
    title: str
    status: str
    updated_at: str
    file_path: Optional[str] = None
    book_name: Optional[str] = None
    author_name: Optional[str] = None
    author_email: Optional[str] = None
    
    # ✅ NUEVO: campos de fecha límite
    deadline_at: Optional[str] = None
    deadline_stage: Optional[str] = None
    days_remaining: Optional[int] = None
    is_overdue: Optional[bool] = False
    
    class Config:
        from_attributes = True