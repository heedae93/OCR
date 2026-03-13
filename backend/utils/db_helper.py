"""
Database helper functions for job tracking
"""
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any
from database import SessionLocal, Job, OCRPage, User, Session, SessionDocument

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
            if job.started_at:
                job.processing_time_seconds = (job.completed_at - job.started_at).total_seconds()

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
