# app/services/dictamen_pdf.py
import os
from datetime import datetime
from docxtpl import DocxTemplate, InlineImage
from docx.shared import Mm
from docx2pdf import convert

STORAGE_DIR = os.getenv("STORAGE_DIR", "storage")
DICTAMENES_DIR = os.path.join(STORAGE_DIR, "dictamenes")
TEMPLATES_DIR = os.path.join(STORAGE_DIR, "templates")

os.makedirs(DICTAMENES_DIR, exist_ok=True)
os.makedirs(TEMPLATES_DIR, exist_ok=True)

def _safe_filename(s: str) -> str:
    s = (s or "").strip()
    out = "".join(c for c in s if c.isalnum() or c in (" ", "-", "_")).strip()
    return out.replace(" ", "_") or "documento"

def public_url(path: str) -> str:
    rel = path.replace("\\", "/")
    if rel.startswith("storage/"):
        rel = rel[len("storage/"):]
    return f"/api/storage/{rel}"

def render_dictamen_docx(
    template_path: str,
    out_docx_path: str,
    context: dict,
    signature_path: str | None = None,
    signature_width_mm: int = 35,
):
    tpl = DocxTemplate(template_path)

    # Si hay firma (PNG), la metemos como imagen
    if signature_path and os.path.exists(signature_path):
        context = dict(context)
        context["firma_dictaminador"] = InlineImage(
            tpl,
            signature_path,
            width=Mm(signature_width_mm),
        )
    else:
        # si el DOCX tiene un placeholder y no hay firma, déjalo vacío
        context = dict(context)
        context.setdefault("firma_dictaminador", "")

    tpl.render(context)
    tpl.save(out_docx_path)

def docx_to_pdf(docx_path: str, pdf_path: str):
    # docx2pdf convierte con Word (Windows)
    # convert(input, output)
    convert(docx_path, pdf_path)

def generate_dictamen_pdf(
    *,
    template_filename: str,
    folio: str,
    chapter_title: str,
    book_name: str,
    author_name: str,
    author_email: str,
    evaluator_name: str,
    evaluator_email: str,
    place_and_date: str,
    asunto: str,
    body_text: str,
    start_date: str,
    end_date: str,
    cargo: str,
    signature_path: str | None = None,
):
    template_path = os.path.join(TEMPLATES_DIR, template_filename)
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"No existe la plantilla en: {template_path}")

    stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    safe = _safe_filename(f"{folio}_{chapter_title}")
    out_docx = os.path.join(DICTAMENES_DIR, f"dictamen_{safe}_{stamp}.docx")
    out_pdf  = os.path.join(DICTAMENES_DIR, f"dictamen_{safe}_{stamp}.pdf")

    context = {
        "folio": folio,
        "chapter_title": chapter_title,
        "book_name": book_name,
        "author_name": author_name,
        "author_email": author_email,
        "evaluator_name": evaluator_name,
        "evaluator_email": evaluator_email,
        "place_and_date": place_and_date,
        "asunto": asunto,
        "body_text": body_text,
        "start_date": start_date,
        "end_date": end_date,
        "cargo": cargo,
        # "firma_dictaminador" se llena arriba si hay signature_path
    }

    render_dictamen_docx(template_path, out_docx, context, signature_path=signature_path)
    docx_to_pdf(out_docx, out_pdf)

    return {
        "docx_path": public_url(out_docx),
        "pdf_path": public_url(out_pdf),
        "physical_docx": out_docx,
        "physical_pdf": out_pdf,
    }