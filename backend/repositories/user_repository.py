from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.db.models import User


def get_all_users(db: Session) -> list[User]:
    return db.query(User).all()


def get_user_by_id(
    db: Session,
    user_id: int,
) -> User | None:
    return (
        db.query(User)
        .filter(User.id == user_id)
        .first()
    )


def get_user_by_email(
    db: Session,
    email: str,
) -> User | None:
    return (
        db.query(User)
        .filter(User.email == email)
        .first()
    )


def create_user(
    db: Session,
    email: str,
    full_name: str,
) -> User:
    user = User(
        email=email,
        full_name=full_name,
    )

    db.add(user)

    try:
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        raise

    return user
