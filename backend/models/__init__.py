"""
Data models for OCR Gen application
"""
from .job import Job, JobStatus, JobCreate, JobResponse
from .ocr import OCRLine, OCRPage, OCRResult
from .document import Document, DocumentMetadata

__all__ = [
    "Job",
    "JobStatus",
    "JobCreate",
    "JobResponse",
    "OCRLine",
    "OCRPage",
    "OCRResult",
    "Document",
    "DocumentMetadata",
]
