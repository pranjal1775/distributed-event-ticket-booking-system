import os
import time
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase

logger = logging.getLogger(__name__)

# Module-level references — tests can replace these before the app starts
engine       = None
SessionLocal = None


class Base(DeclarativeBase):
    pass


def get_db_url() -> str:
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    db   = os.getenv("POSTGRES_DB", "ticketdb")
    user = os.getenv("POSTGRES_USER", "ticketuser")
    pwd  = os.getenv("POSTGRES_PASSWORD", "changeme")
    return f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{db}"


def init_db(retries: int = 10, delay: int = 2):
    """
    Called once at application startup.
    Tests replace `engine` and `SessionLocal` before calling this,
    so this function is skipped when those are already set.
    """
    global engine, SessionLocal

    if engine is not None:
        return  # already initialised (e.g. by test override)

    url = get_db_url()
    for attempt in range(1, retries + 1):
        try:
            _engine = create_engine(url, pool_pre_ping=True)
            with _engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            engine       = _engine
            SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
            logger.info("[user-service] Database connection established")
            return
        except Exception as exc:
            logger.warning(
                "[user-service] DB not ready (attempt %d/%d): %s",
                attempt, retries, exc,
            )
            if attempt == retries:
                raise
            time.sleep(delay)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
