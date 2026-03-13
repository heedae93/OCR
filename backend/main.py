"""
FastAPI main application for BBOCR
"""
import os
import logging

# Load config first to get GPU settings
from config import Config

# Set CUDA_VISIBLE_DEVICES from config (before importing paddle)
os.environ['CUDA_VISIBLE_DEVICES'] = Config.CUDA_VISIBLE_DEVICES

# Set cuDNN/cuBLAS library paths
if not Config.GPU_AUTO_DETECT_LIBS:
    # Use manually specified paths from config.yaml
    cudnn_path = Config.GPU_CUDNN_LIB_PATH
    cublas_path = Config.GPU_CUBLAS_LIB_PATH
    if cudnn_path or cublas_path:
        current_ld_path = os.environ.get('LD_LIBRARY_PATH', '')
        parts = [p for p in [cudnn_path, cublas_path, current_ld_path] if p]
        os.environ['LD_LIBRARY_PATH'] = ':'.join(parts)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# CTC patch (must be applied before PaddleOCR import)
from core.ctc_patch import patch_ctc_decoder
patch_ctc_decoder()

from api import ocr, storage, drive, jobs, sessions, settings, export
from database import init_db

# Configure logging
logging.basicConfig(
    level=getattr(logging, 'INFO'),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="BBOCR API",
    description="Powerful multilingual OCR with searchable PDF generation",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=Config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(ocr.router, prefix="/api", tags=["OCR"])
app.include_router(storage.router, prefix="/api", tags=["Storage"])
app.include_router(drive.router, tags=["Drive"])
app.include_router(jobs.router, prefix="/api", tags=["Jobs"])
app.include_router(sessions.router, prefix="/api", tags=["Sessions"])
app.include_router(settings.router, tags=["Settings"])
app.include_router(export.router, tags=["Export"])

# Mount static files
try:
    app.mount(
        "/files/processed",
        StaticFiles(directory=str(Config.PROCESSED_DIR)),
        name="processed"
    )
    logger.info("Mounted processed files directory")
except Exception as e:
    logger.warning(f"Failed to mount processed files: {e}")


@app.on_event("startup")
async def startup_event():
    """Application startup"""
    logger.info("=" * 60)
    logger.info("BBOCR API Starting...")
    logger.info(f"Backend URL: http://{Config.BACKEND_HOST}:{Config.BACKEND_PORT}")
    logger.info(f"Data directory: {Config.DATA_DIR}")
    logger.info(f"CUDA_VISIBLE_DEVICES: {Config.CUDA_VISIBLE_DEVICES}")
    logger.info(f"Available GPU IDs: {Config.AVAILABLE_GPU_IDS}")
    logger.info("=" * 60)

    # Ensure directories exist
    Config.ensure_directories()
    logger.info("Data directories verified")

    # Initialize database
    try:
        init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")

    # Pre-load OCR models for all GPUs at startup
    logger.info("=" * 60)
    logger.info("Pre-loading OCR models for faster processing...")
    try:
        from api.ocr import preload_all_models
        await preload_all_models()
        logger.info("All OCR models pre-loaded successfully!")
    except Exception as e:
        logger.error(f"Failed to pre-load OCR models: {e}")
        logger.warning("Models will be loaded on first request (slower)")
    logger.info("=" * 60)


@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown"""
    logger.info("BBOCR API shutting down...")


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "name": "BBOCR API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "message": "BBOCR API is running"
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=Config.BACKEND_HOST,
        port=Config.BACKEND_PORT,
        reload=True,
        log_level="info"
    )
