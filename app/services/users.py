from sqlalchemy import select, insert

from app.database import SessionLocal
from app.models import User

def create_user(email: str, password_hash: str) -> int:

    db = SessionLocal()

    try:
        statement = insert(User).values(
            email = email,
            password_hash= password_hash,
        )

        result = db.execute(statement)
        db.commit()

        return result.inserted_primary_key[0]
    
    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


def get_user_by_email(email:str) -> User | None:
    db = SessionLocal()

    try:
        statement = select(User).where(User.email == email)

        result = db.execute(statement)

        return result.scalar_one_or_none()

    finally:
        db.close()