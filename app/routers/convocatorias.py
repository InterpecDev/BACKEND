import os
import io
import re
from datetime import datetime
from typing import List, Optional, Dict

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from pypdf import PdfReader, PdfWriter

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.platypus import (
    BaseDocTemplate,
    PageTemplate,
    Frame,
    Paragraph,
    Spacer,
    ListFlowable,
    ListItem,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from app.db.session import get_db
from app.core.deps import get_current_user
from app.models.convocatoria import Convocatoria
from app.schemas.convocatoria import ConvocatoriaUpsert

router = APIRouter(prefix="/convocatorias", tags=["convocatorias"])

STORAGE_DIR = os.getenv("STORAGE_DIR", "storage")
CONV_DIR = os.path.join(STORAGE_DIR, "convocatorias")

# ==========================================================
# AJUSTA ESTO SEGÚN TU PLANTILLA PDF
# ==========================================================
FRAME_X = 0.80 * inch
FRAME_Y = 1.10 * inch
FRAME_W = 6.90 * inch
FRAME_H = 8.90 * inch
HEADER_H = 0.55 * inch


def _is_editorial(payload: dict) -> bool:
    return (payload or {}).get("role") == "editorial"


def _storage_url_from_disk_path(disk_path: Optional[str]) -> Optional[str]:
    if not disk_path:
        return None
    rel = disk_path.replace("\\", "/")
    if rel.startswith("storage/"):
        rel = rel[len("storage/"):]
    return f"/api/storage/{rel}"


def _fmt_date_iso_to_ddmmyyyy(iso_str: str) -> str:
    try:
        if not iso_str:
            return ""
        y, m, d = iso_str.split("-")
        return f"{d}/{m}/{y}"
    except Exception:
        return iso_str


def _to_front(row: Convocatoria) -> dict:
    template_name = os.path.basename(row.pdf_path) if row.pdf_path else None
    template_url = _storage_url_from_disk_path(row.pdf_path)

    final_name = os.path.basename(row.final_pdf_path) if row.final_pdf_path else None
    final_url = _storage_url_from_disk_path(row.final_pdf_path)

    updated = row.updated_at or row.created_at

    return {
        "id": int(row.id),
        "year": int(row.year),
        "title": row.title or "",
        "startDate": row.start_date.isoformat() if row.start_date else "",
        "endDate": row.end_date.isoformat() if row.end_date else "",
        "text": row.text or "",
        "description": row.description or "",

        # ✅ frontend espera pdfName/pdfUrl
        "pdfName": template_name,
        "pdfUrl": template_url,

        "finalPdfName": final_name,
        "finalPdfUrl": final_url,

        "updatedAt": updated.isoformat()[:10] if updated else "",
    }


# ==========================================================
# PARSER: text con secciones "=== ... ==="
# ==========================================================
def _parse_fields_from_text(text: str) -> Dict[str, str]:
    t = (text or "").replace("\r\n", "\n").replace("\r", "\n")

    def take(start: str, end: Optional[str] = None) -> str:
        i = t.find(start)
        if i == -1:
            return ""
        from_i = i + len(start)
        j = t.find(end, from_i) if end else -1
        chunk = t[from_i:] if j == -1 else t[from_i:j]
        return chunk.strip()

    return {
        "description": take("=== DESCRIPCIÓN / OBJETIVO ===", "=== REQUISITOS ==="),
        "requirements": take("=== REQUISITOS ===", "=== CORREO DE ENVÍO ==="),
        "submissionEmail": take("=== CORREO DE ENVÍO ===", "=== CONTACTO ==="),
        "contactInfo": take("=== CONTACTO ===", "=== NOTAS ==="),
        "notes": take("=== NOTAS ==="),
    }


# ==========================================================
# ReportLab helpers: escape + inline formatting
# ==========================================================
def _escape_rl(text: str) -> str:
    """Escapa solo &,<,> para que ReportLab no 'rompa' el markup."""
    if not text:
        return ""
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .strip()
    )


def _convert_md_bold_to_tags(text: str) -> str:
    """Convierte **bold** a <b>bold</b> SIN tocar caracteres especiales."""
    if not text:
        return ""
    out = ""
    i = 0
    bold = False
    while i < len(text):
        if text[i:i + 2] == "**":
            out += "<b>" if not bold else "</b>"
            bold = not bold
            i += 2
            continue
        out += text[i]
        i += 1
    if bold:
        out += "</b>"
    return out


def rl_inline(text: str, allow_tags: bool = False) -> str:
    """
    Sanitizador único:
      - allow_tags=False: pensado para texto del usuario. Escapa &,<,> y permite **bold**.
      - allow_tags=True: pensado para strings ya con tags (<b> etc.) que tú construyes.
        En este modo NO debes meter texto del usuario sin escaparlo antes.
    """
    if not text:
        return ""

    text = text.strip()

    if allow_tags:
        # OJO: aquí NO escapamos < y > porque pueden ser tags válidos.
        # Solo escapamos & para evitar & sueltos que rompan.
        # (Los valores de usuario deben ir con _escape_rl)
        return text.replace("&", "&amp;")

    # texto de usuario: primero escapar, luego convertir **bold** -> <b>
    escaped = _escape_rl(text)
    # _escape_rl escapó < y >, así que **bold** no se pierde
    # pero necesitamos convertir ** ** en tags ya escapados: sigue funcionando.
    return _convert_md_bold_to_tags(escaped)


def rl_b(label: str, value: str) -> str:
    """Devuelve '<b>Label:</b> value' escapando el value correctamente."""
    return f"<b>{_escape_rl(label)}:</b> {_escape_rl(value)}"


# ==========================================================
# Markdown básico -> Flowables
# ==========================================================
_H_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_UL_RE = re.compile(r"^(\s*)[-*•]\s+(.+?)\s*$")
_OL_RE = re.compile(r"^(\s*)(\d+)\.\s+(.+?)\s*$")
_HR_RE = re.compile(r"^\s*(---|\*\*\*|___)\s*$")


def _md_to_story(md: str, styles) -> list:
    """
    Markdown básico -> Flowables
    Soporta:
      - ## / ### headings
      - listas: - item / * item / • item
      - listas numeradas: 1. item
      - --- separador
      - párrafos (une líneas hasta blanco)
      - **negritas**
    """
    md = (md or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not md:
        return [Paragraph("—", styles["C_BODY"])]

    story = []
    lines = md.split("\n")

    para_buf: list[str] = []
    ul_items: list[str] = []
    ol_items: list[str] = []
    ol_start = 1

    def flush_paragraph():
        nonlocal para_buf
        if not para_buf:
            return
        text = " ".join(x.strip() for x in para_buf if x.strip())
        if text:
            story.append(Paragraph(rl_inline(text), styles["C_BODY"]))
            story.append(Spacer(1, 6))
        para_buf = []

    def flush_ul():
        nonlocal ul_items
        if not ul_items:
            return
        items = [
            ListItem(Paragraph(rl_inline(x), styles["C_BODY"]))
            for x in ul_items
        ]
        story.append(ListFlowable(
            items,
            bulletType="bullet",
            leftIndent=16,
            bulletFontName="Helvetica",
            bulletFontSize=10,
            bulletOffsetY=1,
        ))
        story.append(Spacer(1, 8))
        ul_items = []

    def flush_ol():
        nonlocal ol_items, ol_start
        if not ol_items:
            return
        items = [
            ListItem(Paragraph(rl_inline(x), styles["C_BODY"]))
            for x in ol_items
        ]
        story.append(ListFlowable(
            items,
            bulletType="1",
            start=ol_start,
            leftIndent=18,
            bulletFontName="Helvetica",
            bulletFontSize=10,
            bulletOffsetY=1,
        ))
        story.append(Spacer(1, 8))
        ol_items = []
        ol_start = 1

    for raw in lines:
        line = raw.rstrip()

        # blank line
        if not line.strip():
            flush_ul()
            flush_ol()
            flush_paragraph()
            continue

        # hr
        if _HR_RE.match(line):
            flush_ul()
            flush_ol()
            flush_paragraph()
            story.append(Spacer(1, 6))
            story.append(Paragraph("<font color='#9CA3AF'>______________________________</font>", styles["C_SMALL"]))
            story.append(Spacer(1, 10))
            continue

        # heading
        hm = _H_RE.match(line)
        if hm:
            flush_ul()
            flush_ol()
            flush_paragraph()
            level = len(hm.group(1))
            txt = hm.group(2).strip()
            if level <= 2:
                story.append(Paragraph(rl_inline(txt), styles["C_H2"]))
                story.append(Spacer(1, 4))
            else:
                story.append(Paragraph(rl_inline(f"**{txt}**"), styles["C_BODY"]))
                story.append(Spacer(1, 2))
            continue

        # unordered list
        um = _UL_RE.match(line)
        if um:
            flush_paragraph()
            flush_ol()
            ul_items.append(um.group(2).strip())
            continue

        # ordered list
        om = _OL_RE.match(line)
        if om:
            flush_paragraph()
            flush_ul()
            num = int(om.group(2))
            if not ol_items:
                ol_start = num
            ol_items.append(om.group(3).strip())
            continue

        # normal text
        para_buf.append(line)

    flush_ul()
    flush_ol()
    flush_paragraph()
    return story


def _make_styles():
    base = getSampleStyleSheet()

    base.add(ParagraphStyle(
        name="C_H1",
        parent=base["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=17,
        textColor=colors.HexColor("#0F3D3E"),
        spaceAfter=6,
    ))

    base.add(ParagraphStyle(
        name="C_H2",
        parent=base["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=11.5,
        leading=14,
        textColor=colors.HexColor("#111827"),
        spaceBefore=6,
        spaceAfter=6,
    ))

    base.add(ParagraphStyle(
        name="C_BODY",
        parent=base["BodyText"],
        fontName="Helvetica",
        fontSize=10.5,
        leading=14.5,
        textColor=colors.HexColor("#111827"),
        alignment=TA_JUSTIFY,
    ))

    base.add(ParagraphStyle(
        name="C_SMALL",
        parent=base["BodyText"],
        fontName="Helvetica",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#374151"),
    ))

    return base


def _make_overlay_pdf(data: dict) -> bytes:
    packet = io.BytesIO()
    styles = _make_styles()

    title = (data.get("title") or "").strip() or "Convocatoria"
    year = str(data.get("year") or "")
    start = _fmt_date_iso_to_ddmmyyyy(data.get("startDate") or "")
    end = _fmt_date_iso_to_ddmmyyyy(data.get("endDate") or "")

    fields = _parse_fields_from_text(data.get("text") or "")
    description = fields["description"]
    requirements = fields["requirements"]
    submission_email = fields["submissionEmail"]
    contact_info = fields["contactInfo"]
    notes = fields["notes"]

    story: list = []

    # ---- Título + meta (AQUÍ YA NO SALEN LOS TAGS CON SÍMBOLOS)
    story.append(Paragraph(rl_inline(title), styles["C_H1"]))
    story.append(Spacer(1, 6))
    story.append(Paragraph(rl_inline(rl_b("Año", year), allow_tags=True), styles["C_SMALL"]))
    story.append(Paragraph(
        rl_inline(f"<b>Vigencia:</b> {_escape_rl(start)} \u2192 {_escape_rl(end)}", allow_tags=True),
        styles["C_SMALL"]
    ))
    story.append(Spacer(1, 10))

    # ---- Descripción
    if description.strip():
        story.append(Paragraph("Descripción / objetivo", styles["C_H2"]))
        story.extend(_md_to_story(description, styles))

    # ---- Requisitos
    if requirements.strip():
        story.append(Paragraph("Requisitos", styles["C_H2"]))
        story.extend(_md_to_story(requirements, styles))

    # ---- Contacto / Envío (sin símbolos)
    if submission_email.strip() or contact_info.strip():
        story.append(Paragraph("Contacto / Envío", styles["C_H2"]))

        if submission_email.strip():
            story.append(Paragraph(
                rl_inline(rl_b("Correo", submission_email.strip()), allow_tags=True),
                styles["C_BODY"]
            ))
            story.append(Spacer(1, 4))

        if contact_info.strip():
            story.append(Paragraph(
                rl_inline(rl_b("Contacto", contact_info.strip()), allow_tags=True),
                styles["C_BODY"]
            ))
            story.append(Spacer(1, 8))

    # ---- Notas
    if notes.strip():
        story.append(Paragraph("Notas", styles["C_H2"]))
        story.extend(_md_to_story(notes, styles))

    if not (
        description.strip() or requirements.strip()
        or submission_email.strip() or contact_info.strip() or notes.strip()
    ):
        story.append(Paragraph("Sin contenido. Completa el formulario en el sistema.", styles["C_SMALL"]))

    frame = Frame(
        FRAME_X, FRAME_Y, FRAME_W, FRAME_H,
        leftPadding=0, rightPadding=0,
        topPadding=HEADER_H, bottomPadding=0,
        showBoundary=0,
    )

    def _on_page(c, doc):
        header_y = FRAME_Y + FRAME_H - HEADER_H
        c.saveState()

        c.setFillColor(colors.HexColor("#0F3D3E"))
        c.roundRect(FRAME_X, header_y, FRAME_W, HEADER_H, 10, fill=1, stroke=0)

        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(FRAME_X + 12, header_y + (HEADER_H / 2) - 4, "Convocatoria (vista final)")

        c.setStrokeColor(colors.HexColor("#E5E7EB"))
        c.setLineWidth(1)
        c.line(FRAME_X, header_y - 6, FRAME_X + FRAME_W, header_y - 6)

        c.restoreState()

    doc = BaseDocTemplate(
        packet,
        pagesize=letter,
        leftMargin=0, rightMargin=0, topMargin=0, bottomMargin=0,
    )
    doc.addPageTemplates([PageTemplate(id="overlay", frames=[frame], onPage=_on_page)])
    doc.build(story)

    packet.seek(0)
    return packet.read()


# ==========================================================
# ENDPOINTS
# ==========================================================
@router.get("", response_model=List[dict])
def list_convocatorias(
    only_active: bool = True,
    db: Session = Depends(get_db),
    _user=Depends(get_current_user),
):
    q = db.query(Convocatoria)
    if only_active:
        q = q.filter(Convocatoria.active == 1)
    rows = q.order_by(Convocatoria.year.desc(), Convocatoria.id.desc()).all()
    return [_to_front(r) for r in rows]


@router.post("", response_model=dict)
def create_convocatoria(
    payload: ConvocatoriaUpsert,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    if not _is_editorial(user):
        raise HTTPException(status_code=403, detail="No autorizado.")

    row = Convocatoria(
        year=int(payload.year),
        title=payload.title,
        start_date=payload.start_date,
        end_date=payload.end_date,
        text=payload.text or "",
        description=payload.description or "",
        active=int(payload.active),
        updated_at=datetime.utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_front(row)


@router.put("/{conv_id}", response_model=dict)
def update_convocatoria(
    conv_id: int,
    payload: ConvocatoriaUpsert,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    if not _is_editorial(user):
        raise HTTPException(status_code=403, detail="No autorizado.")

    row = db.query(Convocatoria).filter(Convocatoria.id == conv_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Convocatoria no encontrada.")

    row.year = int(payload.year)
    row.title = payload.title
    row.start_date = payload.start_date
    row.end_date = payload.end_date
    row.text = payload.text or ""
    row.description = payload.description or ""
    row.active = int(payload.active)
    row.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(row)
    return _to_front(row)


@router.post("/{conv_id}/pdf", response_model=dict)
async def upload_template_pdf(
    conv_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    if not _is_editorial(user):
        raise HTTPException(status_code=403, detail="No autorizado.")
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Solo se permite PDF.")

    row = db.query(Convocatoria).filter(Convocatoria.id == conv_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Convocatoria no encontrada.")

    os.makedirs(CONV_DIR, exist_ok=True)

    safe_name = f"conv_template_{row.year}_{conv_id}.pdf"
    disk_path = os.path.join(CONV_DIR, safe_name)

    content = await file.read()
    with open(disk_path, "wb") as f:
        f.write(content)

    row.pdf_path = f"storage/convocatorias/{safe_name}"
    row.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(row)
    return _to_front(row)


@router.post("/{conv_id}/generate", response_model=dict)
def generate_final_pdf(
    conv_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    if not _is_editorial(user):
        raise HTTPException(status_code=403, detail="No autorizado.")

    row = db.query(Convocatoria).filter(Convocatoria.id == conv_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Convocatoria no encontrada.")

    if not row.pdf_path:
        raise HTTPException(status_code=400, detail="Primero sube la plantilla PDF.")

    os.makedirs(CONV_DIR, exist_ok=True)

    template_path = row.pdf_path.replace("\\", "/")
    if not template_path.startswith("storage/"):
        template_path = f"storage/{template_path}"

    out_name = f"conv_final_{row.year}_{conv_id}.pdf"
    out_disk_path = os.path.join(CONV_DIR, out_name)

    reader = PdfReader(template_path)
    writer = PdfWriter()

    data = _to_front(row)

    overlay_bytes = _make_overlay_pdf(data)
    overlay_reader = PdfReader(io.BytesIO(overlay_bytes))
    overlay_page = overlay_reader.pages[0]

    base_page = reader.pages[0]
    base_page.merge_page(overlay_page)
    writer.add_page(base_page)

    for i in range(1, len(reader.pages)):
        writer.add_page(reader.pages[i])

    with open(out_disk_path, "wb") as f:
        writer.write(f)

    row.final_pdf_path = f"storage/convocatorias/{out_name}"
    row.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(row)

    return {
        "ok": True,
        "finalPdfName": out_name,
        "finalPdfUrl": _storage_url_from_disk_path(row.final_pdf_path),
    }
