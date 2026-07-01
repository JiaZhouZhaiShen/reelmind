"""Database session factories for AI container.

Provides both SQLite (AI results) and PostgreSQL (asset metadata) sessions.
"""
from __future__ import annotations
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# ── PostgreSQL (read Asset + SystemSetting) ──────────────────────────────────
PGBase = declarative_base()

class Asset(PGBase):
    __tablename__ = "assets"
    from sqlalchemy import Column, String, Float, Integer, BigInteger, Boolean, DateTime, Text
    from sqlalchemy.dialects.postgresql import UUID
    id = Column(UUID(as_uuid=True), primary_key=True)
    library_id = Column(UUID(as_uuid=True), nullable=False)
    original_path = Column(String(2048), nullable=False)
    file_name = Column(String(512), nullable=False)
    file_size = Column(BigInteger, nullable=False)
    mime_type = Column(String(64))
    duration = Column(Float)
    width = Column(Integer)
    height = Column(Integer)
    fps = Column(Float)
    has_audio = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True))

class AIEngineJob(PGBase):
    __tablename__ = "ai_engine_jobs"
    from sqlalchemy import Column, BigInteger, Integer, String, Text, DateTime
    from sqlalchemy.dialects.postgresql import UUID, ARRAY
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    media_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    engine_name = Column(String(32), nullable=False)
    status = Column(String(16), nullable=False, default="pending", index=True)
    depends_on = Column(ARRAY(String), default=list, nullable=False)
    retry_count = Column(Integer, default=0, nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

class SystemSetting(PGBase):
    __tablename__ = "system_settings"
    from sqlalchemy import Column, String, Text, DateTime
    from sqlalchemy.dialects.postgresql import UUID
    id = Column(UUID(as_uuid=True), primary_key=True)
    key = Column(String(128), unique=True, nullable=False)
    value = Column(Text)
    value_type = Column(String(16), nullable=False, default="string")
    category = Column(String(64), default="general")

_pg_engine = None

def get_pg_engine():
    global _pg_engine
    if _pg_engine is None:
        host = os.environ.get("DB_HOST", "postgres")
        port = os.environ.get("DB_PORT", "5432")
        user = os.environ.get("DB_USER", "reelmind")
        password = os.environ.get("DB_PASSWORD", "reelmind")
        db = os.environ.get("DB_NAME", "reelmind")
        url = f"postgresql://{user}:{password}@{host}:{port}/{db}"
        _pg_engine = create_engine(url, pool_size=2, max_overflow=2, pool_pre_ping=True)
    return _pg_engine

def get_pg_session():
    Session = sessionmaker(bind=get_pg_engine())
    return Session()

_sqlite_engine = None

from sqlalchemy import event as _sqlite_event


def get_sqlite_engine():
    global _sqlite_engine
    if _sqlite_engine is None:
        data_root = os.environ.get("DATA_ROOT", "")
        if data_root:
            db_path = os.path.join(data_root, "reelmind_ai.db")
        else:
            db_path = os.path.join(os.getcwd(), "data", "reelmind_ai.db")
        _sqlite_engine = create_engine("sqlite:///" + db_path, echo=False)

        _sqlite_event.listens_for(_sqlite_engine, "connect")
        def _set_sqlite_wal(dbapi_connection, connection_record):
            """Enable WAL mode for better concurrent access."""
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.execute("PRAGMA cache_size=-64000")
            cursor.close()

        from .ai_models import AIBase
        AIBase.metadata.create_all(_sqlite_engine)
    return _sqlite_engine

def get_sqlite_session():
    Session = sessionmaker(bind=get_sqlite_engine())
    return Session()
