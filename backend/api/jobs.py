"""
Jobs API endpoints - Database-backed job management
"""
import logging
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, or_, func

from database import get_db, Job, OCRPage, User
from models.job import JobResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/jobs", response_model=List[JobResponse])
async def list_jobs(
    user_id: str = "default",
    status: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(50, le=100),
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """
    List jobs with filtering and pagination

    Args:
        user_id: User ID (default: "default")
        status: Filter by status (queued, processing, completed, failed)
        search: Search in filename
        limit: Maximum number of results (max 100)
        offset: Offset for pagination
    """
    logger.info(f"list_jobs called: user_id={user_id}, status={status}, search={search}")
    try:
        query = db.query(Job).filter(Job.user_id == user_id)
        logger.info(f"Created query for user_id={user_id}")

        # Filter by status
        if status:
            query = query.filter(Job.status == status)

        # Search in filename
        if search:
            query = query.filter(Job.original_filename.like(f"%{search}%"))

        # Order by creation time (newest first)
        query = query.order_by(desc(Job.created_at))

        # Pagination
        total = query.count()
        jobs = query.offset(offset).limit(limit).all()

        # Convert to response format
        job_responses = []
        for job in jobs:
            job_responses.append(JobResponse(
                job_id=job.job_id,
                filename=job.original_filename,
                status=job.status,
                progress_percent=job.progress_percent,
                current_page=job.current_page,
                total_pages=job.total_pages,
                message=job.error_message if job.status == "failed" else None,
                pdf_url=f"/files/processed/{job.job_id}.pdf" if job.pdf_file_path else None,
                raw_file_url=None,  # Can be added if needed
                created_at=job.created_at.isoformat() if job.created_at else None,
                completed_at=job.completed_at.isoformat() if job.completed_at else None,
                processing_time_seconds=job.processing_time_seconds,
                total_text_blocks=job.total_text_blocks,
                average_confidence=job.average_confidence,
                is_double_column=job.is_double_column
            ))

        logger.info(f"Listed {len(job_responses)} jobs (total: {total})")
        return job_responses

    except Exception as e:
        logger.error(f"Failed to list jobs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: str, db: Session = Depends(get_db)):
    """Get job details by ID"""
    try:
        job = db.query(Job).filter(Job.job_id == job_id).first()

        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        return JobResponse(
            job_id=job.job_id,
            filename=job.original_filename,
            status=job.status,
            progress_percent=job.progress_percent,
            current_page=job.current_page,
            total_pages=job.total_pages,
            message=job.error_message if job.status == "failed" else None,
            pdf_url=f"/files/processed/{job.job_id}.pdf" if job.pdf_file_path else None,
            created_at=job.created_at.isoformat() if job.created_at else None,
            completed_at=job.completed_at.isoformat() if job.completed_at else None,
            processing_time_seconds=job.processing_time_seconds,
            total_text_blocks=job.total_text_blocks,
            average_confidence=job.average_confidence,
            is_double_column=job.is_double_column
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get job {job_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: str, db: Session = Depends(get_db)):
    """Delete a job and its associated files"""
    try:
        job = db.query(Job).filter(Job.job_id == job_id).first()

        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        # Delete associated files
        from pathlib import Path
        files_to_delete = [
            job.raw_file_path,
            job.pdf_file_path,
            job.final_pdf_path,
            job.ocr_json_path
        ]

        deleted_files = 0
        for file_path in files_to_delete:
            if file_path:
                try:
                    path = Path(file_path)
                    if path.exists():
                        path.unlink()
                        deleted_files += 1
                except Exception as e:
                    logger.warning(f"Failed to delete file {file_path}: {e}")

        # Delete from database (cascade will delete pages)
        db.delete(job)
        db.commit()

        logger.info(f"Deleted job {job_id} ({deleted_files} files)")
        return {"message": f"Job deleted successfully ({deleted_files} files removed)"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete job {job_id}: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/jobs/statistics/summary")
async def get_statistics(user_id: str = "default", db: Session = Depends(get_db)):
    """Get job statistics for a user"""
    try:
        # Total jobs
        total_jobs = db.query(func.count(Job.job_id)).filter(Job.user_id == user_id).scalar()

        # Jobs by status
        status_counts = db.query(Job.status, func.count(Job.job_id)).filter(
            Job.user_id == user_id
        ).group_by(Job.status).all()

        # Total pages processed
        total_pages = db.query(func.sum(Job.total_pages)).filter(
            Job.user_id == user_id,
            Job.status == "completed"
        ).scalar() or 0

        # Average processing time
        avg_processing_time = db.query(func.avg(Job.processing_time_seconds)).filter(
            Job.user_id == user_id,
            Job.status == "completed"
        ).scalar() or 0

        # Storage used
        storage_used = db.query(func.sum(Job.file_size_bytes)).filter(
            Job.user_id == user_id
        ).scalar() or 0

        return {
            "total_jobs": total_jobs,
            "status_counts": {status: count for status, count in status_counts},
            "total_pages_processed": total_pages,
            "average_processing_time_seconds": float(avg_processing_time) if avg_processing_time else 0,
            "storage_used_bytes": storage_used,
            "storage_used_mb": round(storage_used / (1024 * 1024), 2)
        }

    except Exception as e:
        logger.error(f"Failed to get statistics: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/jobs/{job_id}/tags")
async def update_job_tags(job_id: str, tags: List[str], db: Session = Depends(get_db)):
    """Update job tags"""
    try:
        job = db.query(Job).filter(Job.job_id == job_id).first()

        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        import json
        job.tags = json.dumps(tags, ensure_ascii=False)
        db.commit()

        return {"message": "Tags updated", "tags": tags}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update tags for job {job_id}: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/jobs/{job_id}/notes")
async def update_job_notes(job_id: str, notes: str, db: Session = Depends(get_db)):
    """Update job notes"""
    try:
        job = db.query(Job).filter(Job.job_id == job_id).first()

        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

        job.notes = notes
        db.commit()

        return {"message": "Notes updated", "notes": notes}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update notes for job {job_id}: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
