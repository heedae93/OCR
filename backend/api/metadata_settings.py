"""
메타데이터 추출 설정 API
"""
import logging
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import Column, String, Boolean, Integer, DateTime
from sqlalchemy.ext.declarative import declarative_base
from database import SessionLocal, Base, engine, get_db

logger = logging.getLogger(__name__)
router = APIRouter()


class MetadataSettings(Base):
    __tablename__ = "metadata_settings"
    __table_args__ = {"extend_existing": True}

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), nullable=False, unique=True)
    extract_full_text = Column(Boolean, default=True)
    extract_language = Column(Boolean, default=True)
    extract_doc_type = Column(Boolean, default=True)
    extract_keywords = Column(Boolean, default=True)
    extract_dates = Column(Boolean, default=True)
    extract_char_count = Column(Boolean, default=True)
    extract_word_count = Column(Boolean, default=True)
    extract_chunks = Column(Boolean, default=True)
    chunk_size = Column(Integer, default=500)
    chunk_overlap = Column(Integer, default=50)
    keywords_top_n = Column(Integer, default=20)
    updated_at = Column(DateTime, default=datetime.now)


class MetadataSettingsSchema(BaseModel):
    extract_full_text: bool = True
    extract_language: bool = True
    extract_doc_type: bool = True
    extract_keywords: bool = True
    extract_dates: bool = True
    extract_char_count: bool = True
    extract_word_count: bool = True
    extract_chunks: bool = True
    chunk_size: int = 500
    chunk_overlap: int = 50
    keywords_top_n: int = 20

    class Config:
        from_attributes = True


DEFAULT_SETTINGS = MetadataSettingsSchema()


def get_user_settings(user_id: str, db: Session) -> MetadataSettingsSchema:
    """유저 설정 조회 (없으면 기본값 반환)"""
    row = db.query(MetadataSettings).filter_by(user_id=user_id).first()
    if not row:
        return DEFAULT_SETTINGS
    return MetadataSettingsSchema.model_validate(row)


@router.get("/metadata-settings")
def get_settings(user_id: str = "default", db: Session = Depends(get_db)):
    return get_user_settings(user_id, db)


@router.put("/metadata-settings")
def update_settings(
    body: MetadataSettingsSchema,
    user_id: str = "default",
    db: Session = Depends(get_db)
):
    row = db.query(MetadataSettings).filter_by(user_id=user_id).first()
    if not row:
        row = MetadataSettings(user_id=user_id)
        db.add(row)

    for field, value in body.model_dump().items():
        setattr(row, field, value)
    row.updated_at = datetime.now()

    db.commit()
    db.refresh(row)
    logger.info(f"Metadata settings updated for user {user_id}")
    return MetadataSettingsSchema.model_validate(row)
