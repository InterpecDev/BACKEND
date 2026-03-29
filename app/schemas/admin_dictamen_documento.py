# app/schemas/admin_dictamen_documento.py
from pydantic import BaseModel
from typing import Optional, Dict, Any, Literal

DictamenStatus = Literal["BORRADOR", "GENERADO", "FIRMADO"]

class AdminDictamenDocumentoOut(BaseModel):
    id: int
    folio: str
    chapterFolio: Optional[str] = None  # ✅ nuevo
    status: DictamenStatus

    template_docx_path: Optional[str] = None
    generated_docx_path: Optional[str] = None
    pdf_path: Optional[str] = None

    recipient_name: Optional[str] = None
    constancia_data_json: Optional[Dict[str, Any]] = None

    capituloId: int
    capitulo: str
    libro: str
    evaluador: str
    
    #NUEVOS
    evaluador_institucion: str | None = None
    evaluador_cvo_snii: str | None = None


class AdminDictamenDocumentoUpdateIn(BaseModel):
    recipient_name: Optional[str] = None
    data: Optional[Dict[str, Any]] = None