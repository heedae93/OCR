"""
Document models
"""
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel


class DocumentMetadata(BaseModel):
    """Document metadata"""
    page_count: int
    file_size: int
    languages: List[str]
    created_at: datetime
    processed_at: Optional[datetime] = None


class Document(BaseModel):
    """Document model"""
    id: str
    filename: str
    original_filename: str
    user_id: str
    status: str
    metadata: DocumentMetadata
    raw_path: Optional[str] = None
    processed_path: Optional[str] = None
    thumbnail_path: Optional[str] = None
