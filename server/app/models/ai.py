"""ReelMind AI data models --- scenes, frames, subtitles, tags, OCR.

These tables use SQLite (by ai_engine), separate from the main PostgreSQL database.
"""
from __future__ import annotations
import uuid
import os
from sqlalchemy import Column, String, Float, Text, Integer, ForeignKey, DateTime, LargeBinary, create_engine
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy import func as sa_func

AIBase = declarative_base()

class Video(AIBase):
    __tablename__ = "videos"
    id = Column(String(36), primary_key=True)
    file_path = Column(String(2048), nullable=False)
    file_name = Column(String(512), nullable=False)
    duration = Column(Float, default=0)
    width = Column(Integer, default=0)
    height = Column(Integer, default=0)
    fps = Column(Float, default=0)
    created_at = Column(DateTime, server_default=sa_func.now())
    updated_at = Column(DateTime, server_default=sa_func.now(), onupdate=sa_func.now())
    scenes = relationship("Scene", back_populates="video", cascade="all, delete-orphan")
    frames = relationship("Frame", back_populates="video", cascade="all, delete-orphan")
    subtitles = relationship("Subtitle", back_populates="video", cascade="all, delete-orphan")

class Scene(AIBase):
    __tablename__ = "scenes"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    video_id = Column(String(36), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False, index=True)
    scene_index = Column(Integer, nullable=False)
    start_time = Column(Float, nullable=False)
    end_time = Column(Float, nullable=False)
    thumbnail_path = Column(String(1024))
    created_at = Column(DateTime, server_default=sa_func.now())
    video = relationship("Video", back_populates="scenes")
    tags = relationship("SceneTag", back_populates="scene", cascade="all, delete-orphan")
    ocr_results = relationship("SceneOCR", back_populates="scene", cascade="all, delete-orphan")

class Frame(AIBase):
    __tablename__ = "frames"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    video_id = Column(String(36), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False, index=True)
    scene_id = Column(String(36), ForeignKey("scenes.id", ondelete="SET NULL"), nullable=True)
    time_sec = Column(Float, nullable=False)
    frame_path = Column(String(1024))
    embedding = Column(LargeBinary, nullable=True)
    created_at = Column(DateTime, server_default=sa_func.now())
    video = relationship("Video", back_populates="frames")

class Subtitle(AIBase):
    __tablename__ = "subtitles"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    video_id = Column(String(36), ForeignKey("videos.id", ondelete="CASCADE"), nullable=False, index=True)
    start = Column(Float, nullable=False)
    end = Column(Float, nullable=False)
    text = Column(Text, nullable=False)
    language = Column(String(8), default="zh")
    speaker = Column(String(64), nullable=True)
    confidence = Column(Float, default=1.0)
    created_at = Column(DateTime, server_default=sa_func.now())
    video = relationship("Video", back_populates="subtitles")

class SceneTag(AIBase):
    __tablename__ = "scene_tags"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    scene_id = Column(String(36), ForeignKey("scenes.id", ondelete="CASCADE"), nullable=False, index=True)
    label = Column(String(128), nullable=False)
    confidence = Column(Float, default=0.0)
    count = Column(Integer, default=1)
    created_at = Column(DateTime, server_default=sa_func.now())
    scene = relationship("Scene", back_populates="tags")

class SceneOCR(AIBase):
    __tablename__ = "scene_ocr"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    scene_id = Column(String(36), ForeignKey("scenes.id", ondelete="CASCADE"), nullable=False, index=True)
    text = Column(Text, nullable=False)
    confidence = Column(Float, default=0.0)
    bbox_x = Column(Float, default=0.0)
    bbox_y = Column(Float, default=0.0)
    bbox_w = Column(Float, default=0.0)
    bbox_h = Column(Float, default=0.0)
    created_at = Column(DateTime, server_default=sa_func.now())
    scene = relationship("Scene", back_populates="ocr_results")

_ai_engine = None

def get_ai_engine(db_path=None):
    global _ai_engine
    if db_path is None:
        data_root = os.environ.get("DATA_ROOT", "")
        if data_root:
            db_path = os.path.join(data_root, "reelmind_ai.db")
        else:
            db_path = os.path.join(os.getcwd(), "data", "reelmind_ai.db")
    if _ai_engine is None:
        _ai_engine = create_engine("sqlite:///" + db_path, echo=False)
        AIBase.metadata.create_all(_ai_engine)
    return _ai_engine

def get_ai_session(db_path=None):
    from sqlalchemy.orm import sessionmaker
    if db_path is None:
        data_root = os.environ.get("DATA_ROOT", "")
        if data_root:
            db_path = os.path.join(data_root, "reelmind_ai.db")
        else:
            db_path = os.path.join(os.getcwd(), "data", "reelmind_ai.db")
    engine = get_ai_engine(db_path)
    Session = sessionmaker(bind=engine)
    return Session()

from contextlib import contextmanager

@contextmanager
def ai_session(db_path=None):
    """AI session context manager that auto-closes, even on exceptions."""
    session = get_ai_session(db_path)
    try:
        yield session
    finally:
        session.close()

