from collections.abc import Callable

from sqlalchemy.orm import Session

from backend.db.database import SessionLocal, get_db


def get_session_factory() -> Callable[[], Session]:
    return SessionLocal


__all__ = ["get_db", "get_session_factory"]
