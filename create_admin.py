from app.db.session import SessionLocal
from app.models.user import User
from app.core.security import hash_password

EMAIL = "admin@editorial.mx"
PASSWORD = "admin123"

def run():
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.email == EMAIL).first()
        if not u:
            u = User(
                name="Admin Editorial",
                email=EMAIL,
                password_hash=hash_password(PASSWORD),
                role="editorial",
                active=1,
            )
            db.add(u)
        else:
            u.password_hash = hash_password(PASSWORD)
            u.active = 1
            u.role = "editorial"
        db.commit()
        print("OK admin listo:", EMAIL, "/", PASSWORD)
    finally:
        db.close()

if __name__ == "__main__":
    run()
