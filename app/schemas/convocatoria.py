from pydantic import BaseModel
from datetime import date
from typing import Optional

class ConvocatoriaUpsert(BaseModel):
    year: int
    title: str
    start_date: date
    end_date: date

    description: Optional[str] = ""
    requirements: Optional[str] = ""
    submission_email: Optional[str] = ""
    contact_info: Optional[str] = ""
    notes: Optional[str] = ""

    text: Optional[str] = ""
    active: int = 1
