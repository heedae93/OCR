"""
Database helper functions for job tracking
"""
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any
import json
from database import SessionLocal, Job, OCRPage, DocumentChunk, User, Session, SessionDocument

logger = logging.getLogger(__name__)


def create_job_in_db(
    job_id: str,
    filename: str,
    file_path: str,
    file_size: int,
    user_id: str = "default"
) -> bool:
    """Create a new job in database"""
    try:
        db = SessionLocal()

        # Check if job already exists
        existing = db.query(Job).filter_by(job_id=job_id).first()
        if existing:
            logger.warning(f"Job {job_id} already exists in database")
            db.close()
            return False

        # Determine file type
        file_type = Path(filename).suffix.lstrip('.').lower()

        # Create job
        job = Job(
            job_id=job_id,
            user_id=user_id,
            original_filename=filename,
            file_type=file_type,
            file_size_bytes=file_size,
            status="queued",
            raw_file_path=file_path
        )

        db.add(job)
        db.commit()
        logger.info(f"Created job {job_id} in database")

        db.close()
        return True

    except Exception as e:
        logger.error(f"Failed to create job in database: {e}")
        return False


def update_job_status(
    job_id: str,
    status: str,
    progress: Optional[float] = None,
    current_page: Optional[int] = None,
    error_message: Optional[str] = None
) -> bool:
    """Update job status"""
    try:
        db = SessionLocal()
        job = db.query(Job).filter_by(job_id=job_id).first()

        if not job:
            logger.warning(f"Job {job_id} not found in database")
            db.close()
            return False

        job.status = status

        if progress is not None:
            job.progress_percent = progress

        if current_page is not None:
            job.current_page = current_page

        if error_message:
            job.error_message = error_message

        if status == "processing" and not job.started_at:
            job.started_at = datetime.now()

        if status == "completed":
            job.completed_at = datetime.now()
            start = job.started_at or job.created_at
            if start:
                # strip timezone info if present to avoid offset-naive/aware mismatch
                start_naive = start.replace(tzinfo=None) if start.tzinfo else start
                completed_naive = job.completed_at.replace(tzinfo=None)
                job.processing_time_seconds = (completed_naive - start_naive).total_seconds()

        db.commit()
        db.close()
        return True

    except Exception as e:
        logger.error(f"Failed to update job status: {e}")
        return False


def update_job_ocr_results(
    job_id: str,
    ocr_data: Dict[str, Any],
    pdf_path: Optional[str] = None,
    ocr_json_path: Optional[str] = None
) -> bool:
    """Update job with OCR results"""
    try:
        db = SessionLocal()
        job = db.query(Job).filter_by(job_id=job_id).first()

        if not job:
            logger.warning(f"Job {job_id} not found in database")
            db.close()
            return False

        # Update job metadata
        job.total_pages = ocr_data.get('page_count', 0)
        job.total_text_blocks = ocr_data.get('total_bboxes', 0)

        if pdf_path:
            job.pdf_file_path = pdf_path

        if ocr_json_path:
            job.ocr_json_path = ocr_json_path

        # Calculate average confidence
        total_conf = 0
        count = 0
        for page_data in ocr_data.get('pages', []):
            for line in page_data.get('lines', []):
                conf = line.get('confidence')
                if conf is not None:
                    total_conf += conf
                    count += 1

        if count > 0:
            job.average_confidence = total_conf / count

        # Add page information
        for page_data in ocr_data.get('pages', []):
            # Check if page already exists
            existing_page = db.query(OCRPage).filter_by(
                job_id=job_id,
                page_number=page_data.get('page_number', 1)
            ).first()

            if existing_page:
                continue

            page = OCRPage(
                job_id=job_id,
                page_number=page_data.get('page_number', 1),
                width=page_data.get('width', 0),
                height=page_data.get('height', 0),
                text_block_count=len(page_data.get('lines', [])),
                is_multi_column=page_data.get('is_multi_column', False),
                column_boundary=page_data.get('column_boundary')
            )
            db.add(page)

        db.commit()
        logger.info(f"Updated OCR results for job {job_id}")

        # 메타데이터 추출 및 저장
        try:
            from utils.metadata_extractor import extract_all_metadata
            from api.metadata_settings import get_user_settings

            # 유저 설정 로드
            settings = get_user_settings(job.user_id, db)
            meta = extract_all_metadata(
                ocr_data,
                chunk_size=settings.chunk_size,
                chunk_overlap=settings.chunk_overlap,
                keywords_top_n=settings.keywords_top_n,
            )

            if settings.extract_full_text:
                job.full_text = meta["full_text"]
            if settings.extract_language:
                job.detected_language = meta["detected_language"]
            if settings.extract_doc_type:
                job.doc_type = meta["doc_type"]
            if settings.extract_keywords:
                job.keywords = json.dumps(meta["keywords"], ensure_ascii=False)
            if settings.extract_dates:
                job.detected_dates = json.dumps(meta["detected_dates"], ensure_ascii=False)
            if settings.extract_char_count:
                job.char_count = meta["char_count"]
            if settings.extract_word_count:
                job.word_count = meta["word_count"]

            # 청크 저장
            if settings.extract_chunks:
                db.query(DocumentChunk).filter_by(job_id=job_id).delete()
                for chunk in meta["chunks"]:
                    db.add(DocumentChunk(
                        job_id=job_id,
                        chunk_index=chunk["chunk_index"],
                        text=chunk["text"],
                        page_number=chunk["page_number"],
                        char_start=chunk["char_start"],
                        char_end=chunk["char_end"],
                    ))

            db.commit()
            logger.info(
                f"Metadata saved for job {job_id}: "
                f"lang={meta['detected_language']}, doc_type={meta['doc_type']}, "
                f"keywords={len(meta['keywords'])}, chunks={len(meta['chunks'])}"
            )
        except Exception as meta_err:
            logger.error(f"Metadata extraction failed for job {job_id}: {meta_err}")

        db.close()
        return True

    except Exception as e:
        logger.error(f"Failed to update OCR results: {e}")
        return False


def ensure_default_user():
    """Ensure default user exists"""
    try:
        db = SessionLocal()
        user = db.query(User).filter_by(user_id="default").first()

        if not user:
            user = User(
                user_id="default",
                username="default_user",
                email="default@ocr-gen.local"
            )
            db.add(user)
            db.commit()
            logger.info("Created default user")

        db.close()

    except Exception as e:
        logger.error(f"Failed to ensure default user: {e}")


def add_job_to_session(job_id: str, session_id: str = "default") -> bool:
    """Add a job to a session"""
    try:
        db = SessionLocal()

        # Check if job exists
        job = db.query(Job).filter_by(job_id=job_id).first()
        if not job:
            logger.warning(f"Job {job_id} not found")
            db.close()
            return False

        # Check if session exists
        session = db.query(Session).filter_by(session_id=session_id).first()
        if not session:
            logger.warning(f"Session {session_id} not found")
            db.close()
            return False

        # Check if already in session
        existing = db.query(SessionDocument).filter_by(
            session_id=session_id,
            job_id=job_id
        ).first()

        if existing:
            logger.info(f"Job {job_id} already in session {session_id}")
            db.close()
            return True

        # Get max order
        max_order = db.query(SessionDocument).filter_by(
            session_id=session_id
        ).count()

        # Add to session
        session_doc = SessionDocument(
            session_id=session_id,
            job_id=job_id,
            order=max_order,
            is_selected=True
        )

        db.add(session_doc)
        session.updated_at = datetime.now()
        db.commit()

        logger.info(f"Added job {job_id} to session {session_id}")
        db.close()
        return True

    except Exception as e:
        logger.error(f"Failed to add job to session: {e}")
        return False
