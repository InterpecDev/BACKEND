from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, case

from app.db.session import get_db
from app.core.deps import get_current_user

from app.models.user import User
from app.models.book import Book
from app.models.chapter import Chapter

from app.schemas.admin_books import AdminBookOut, AdminChapterOut, AdminAuthorOut


router = APIRouter(prefix="/admin", tags=["admin-books"])


# =========================
# Helpers (mismo estilo que ya usas)
# =========================
def _user_id(db: Session, user_or_payload) -> int:
    # Soporta dict (sub puede ser id o email) o User model
    if not isinstance(user_or_payload, dict):
        return int(user_or_payload.id)

    if user_or_payload.get("id") is not None:
        return int(user_or_payload["id"])

    if user_or_payload.get("user_id") is not None:
        return int(user_or_payload["user_id"])

    sub = user_or_payload.get("sub")

    if isinstance(sub, int):
        return int(sub)

    if isinstance(sub, str) and sub.isdigit():
        return int(sub)

    if isinstance(sub, str) and "@" in sub:
        u = db.query(User).filter(User.email == sub.strip().lower()).first()
        if not u:
            raise HTTPException(status_code=401, detail="Usuario no encontrado")
        return int(u.id)

    raise HTTPException(status_code=401, detail="Token inválido")


def _require_editorial(db: Session, user_or_payload) -> User:
    uid = _user_id(db, user_or_payload)
    me = db.query(User).filter(User.id == uid).first()
    if not me:
        raise HTTPException(status_code=401, detail="Usuario no encontrado")
    if me.role != "editorial":
        raise HTTPException(status_code=403, detail="No autorizado (solo editorial)")
    return me


# =========================
# GET /admin/books
# =========================
@router.get("/books", response_model=list[AdminBookOut])
def admin_list_books(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    _require_editorial(db, user)

    # JOIN books + users(author) + chapters para conteos
    # total_chapters: count(chapters.id)
    # approved: sum(status == 'APROBADO')
    # corrections: sum(status == 'CORRECCIONES')

    rows = (
        db.query(
            Book.id,
            Book.name,
            Book.year,
            Book.created_at,

            User.id.label("author_id"),
            User.name.label("author_name"),
            User.email.label("author_email"),

            func.count(Chapter.id).label("total_chapters"),
            func.coalesce(func.sum(case((Chapter.status == "APROBADO", 1), else_=0)), 0).label("approved"),
            func.coalesce(func.sum(case((Chapter.status == "CORRECCIONES", 1), else_=0)), 0).label("corrections"),
        )
        .join(User, User.id == Book.author_id)
        .outerjoin(Chapter, Chapter.book_id == Book.id)
        .group_by(Book.id, User.id)
        .order_by(Book.year.desc(), Book.id.desc())
        .all()
    )

    out: list[AdminBookOut] = []
    for r in rows:
        out.append(
            AdminBookOut(
                id=int(r.id),
                name=r.name,
                year=int(r.year),
                created_at=str(r.created_at),

                author=AdminAuthorOut(
                    id=int(r.author_id),
                    name=r.author_name,
                    email=r.author_email,
                ),

                total_chapters=int(r.total_chapters or 0),
                approved=int(r.approved or 0),
                corrections=int(r.corrections or 0),
            )
        )

    return out


# =========================
# GET /admin/books/{id}/chapters
# =========================
@router.get("/books/{book_id}/chapters", response_model=list[AdminChapterOut])
def admin_book_chapters(
    book_id: int,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    _require_editorial(db, user)

    # Validar existencia del libro
    b = db.query(Book).filter(Book.id == book_id).first()
    if not b:
        raise HTTPException(status_code=404, detail="Libro no encontrado")

    chapters = (
        db.query(Chapter)
        .filter(Chapter.book_id == book_id)
        .order_by(Chapter.updated_at.desc(), Chapter.id.desc())
        .all()
    )

    # Tu frontend espera author_name/author_email en cada capítulo
    return [
        AdminChapterOut(
            id=int(c.id),
            title=c.title,
            author_name=c.author_name,
            author_email=c.author_email,
            status=c.status,
            updated_at=str(c.updated_at),
        )
        for c in chapters
    ]
