from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.core.config import settings

engine = create_engine(
    settings.database_url,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)
from backend.db.models import Base

Base.metadata.create_all(bind=engine)