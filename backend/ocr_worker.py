"""
Celery Worker for BBOCR OCR processing

실행 방법:
  cd backend
  celery -A ocr_worker worker -Q ocr --loglevel=info --pool=solo

Windows에서는 반드시 --pool=solo 옵션 필요 (fork 미지원)
"""
import os
import sys
import logging

# backend 디렉토리를 Python path에 추가
sys.path.insert(0, os.path.dirname(__file__))

# ── 환경 초기화 (main.py와 동일한 순서로) ──────────────────────
from config import Config

os.environ['CUDA_VISIBLE_DEVICES'] = Config.CUDA_VISIBLE_DEVICES
os.environ.setdefault('PADDLE_PDX_EAGER_INIT', '0')

# langchain 호환 shim (paddlex 내부 의존성)
import types
try:
    from langchain_community.docstore.document import Document as _LCDocument
    _ds_mod = types.ModuleType("langchain.docstore")
    _ds_doc_mod = types.ModuleType("langchain.docstore.document")
    _ds_doc_mod.Document = _LCDocument
    _ds_mod.document = _ds_doc_mod
    sys.modules.setdefault("langchain.docstore", _ds_mod)
    sys.modules.setdefault("langchain.docstore.document", _ds_doc_mod)
except ImportError:
    pass

from core.ctc_patch import patch_ctc_decoder
patch_ctc_decoder()

# ── Celery 앱 및 로거 ──────────────────────────────────────────
from celery_app import celery_app

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def _restore_job_to_manager(job_id: str) -> bool:
    """
    Worker 프로세스의 job_manager는 빈 상태이므로
    DB에서 job 정보를 읽어 메모리에 복원한다.
    """
    from api.ocr import job_manager
    from database import SessionLocal, Job as DBJob

    if job_manager.get_job(job_id):
        return True  # 이미 메모리에 있음

    db = SessionLocal()
    try:
        db_job = db.query(DBJob).filter_by(job_id=job_id).first()
        if not db_job:
            logger.error(f"[Worker] Job {job_id} not found in DB")
            return False
        job_manager.create_job(
            job_id=job_id,
            filename=db_job.original_filename,
            user_id=db_job.user_id or 'worker'
        )
        logger.info(f"[Worker] Restored job {job_id} from DB")
        return True
    finally:
        db.close()


@celery_app.task(
    bind=True,
    name='ocr.process',
    max_retries=2,
    default_retry_delay=30,
    acks_late=True,
)
def process_ocr_task(self, job_id: str):
    """
    OCR 처리 Celery Task

    FastAPI가 Redis 큐에 등록하면 Worker가 꺼내서 실행.
    상태 업데이트는 기존 파일/DB 방식 그대로 유지.
    """
    logger.info(f"[Worker] Task received: job_id={job_id}")

    # Worker 프로세스 job_manager에 job 복원
    if not _restore_job_to_manager(job_id):
        logger.error(f"[Worker] Cannot process job {job_id} - not found in DB")
        return

    try:
        from api.ocr import process_job_task
        process_job_task(job_id)
        logger.info(f"[Worker] Task completed: job_id={job_id}")
    except Exception as exc:
        logger.error(f"[Worker] Task failed: job_id={job_id}, error={exc}", exc_info=True)
        # Celery 재시도 (max_retries 도달 시 FAILED로 처리됨)
        raise self.retry(exc=exc)
