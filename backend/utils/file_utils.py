"""
File utility functions
"""
import uuid
import shutil
from pathlib import Path
from typing import BinaryIO
import logging

logger = logging.getLogger(__name__)


def generate_unique_id() -> str:
    """Generate a unique ID for jobs/files"""
    return str(uuid.uuid4())


def save_uploaded_file(file: BinaryIO, filename: str, destination_dir: Path) -> Path:
    """
    Save an uploaded file to the destination directory

    Args:
        file: File object to save
        filename: Original filename
        destination_dir: Directory to save the file

    Returns:
        Path to the saved file
    """
    try:
        destination_dir.mkdir(parents=True, exist_ok=True)

        # Generate unique filename
        file_id = generate_unique_id()
        file_ext = Path(filename).suffix
        new_filename = f"{file_id}{file_ext}"

        destination_path = destination_dir / new_filename

        # Save file
        with open(destination_path, 'wb') as f:
            shutil.copyfileobj(file, f)

        logger.info(f"File saved: {new_filename}")
        return destination_path

    except Exception as e:
        logger.error(f"Failed to save file: {e}")
        raise


def get_file_size(file_path: Path) -> int:
    """Get file size in bytes"""
    try:
        return file_path.stat().st_size
    except Exception:
        return 0


def cleanup_temp_files(file_paths: list):
    """Clean up temporary files"""
    for file_path in file_paths:
        try:
            path = Path(file_path)
            if path.exists():
                path.unlink()
                logger.debug(f"Cleaned up temp file: {path}")
        except Exception as e:
            logger.warning(f"Failed to clean up {file_path}: {e}")
