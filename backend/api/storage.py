"""
File storage API endpoints
"""
import logging
from pathlib import Path
from typing import List, Dict

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from config import Config

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/files/raw")
async def list_raw_files():
    """List raw uploaded files"""
    try:
        files = []
        for job_dir in Config.RAW_DIR.iterdir():
            if job_dir.is_dir():
                for file_path in job_dir.iterdir():
                    if file_path.is_file():
                        files.append({
                            "name": file_path.name,
                            "path": str(file_path.relative_to(Config.BASE_DIR)),
                            "size": file_path.stat().st_size,
                            "job_id": job_dir.name
                        })
        return {"files": files}
    except Exception as e:
        logger.error(f"Failed to list raw files: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/files/processed")
async def list_processed_files():
    """List processed PDF files"""
    try:
        files = []
        for file_path in Config.PROCESSED_DIR.glob("*.pdf"):
            job_id = file_path.stem
            files.append({
                "name": file_path.name,
                "path": str(file_path.relative_to(Config.BASE_DIR)),
                "size": file_path.stat().st_size,
                "job_id": job_id,
                "url": f"/files/processed/{file_path.name}"
            })
        return {"files": files}
    except Exception as e:
        logger.error(f"Failed to list processed files: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/files/processed/{filename}")
async def download_processed_file(filename: str):
    """Download a processed PDF file"""
    try:
        file_path = Config.PROCESSED_DIR / filename
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="File not found")

        return FileResponse(
            path=str(file_path),
            filename=filename,
            media_type="application/pdf"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to download file: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/files/raw/{job_id}/{filename}")
async def download_raw_file(job_id: str, filename: str):
    """Download a raw uploaded file"""
    try:
        file_path = Config.RAW_DIR / job_id / filename
        if not file_path.exists():
            raise HTTPException(status_code=404, detail="File not found")

        # Determine media type
        suffix = file_path.suffix.lower()
        media_type = "application/octet-stream"
        if suffix == ".pdf":
            media_type = "application/pdf"
        elif suffix in [".png", ".jpg", ".jpeg"]:
            media_type = f"image/{suffix[1:]}"

        return FileResponse(
            path=str(file_path),
            filename=filename,
            media_type=media_type
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to download raw file: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/storage/tree")
async def get_storage_tree():
    """Get file tree for storage explorer"""
    try:
        def build_tree(path: Path, name: str) -> Dict:
            """Build tree structure recursively"""
            if path.is_file():
                return {
                    "name": name,
                    "type": "file",
                    "size": path.stat().st_size,
                    "path": str(path.relative_to(Config.BASE_DIR))
                }
            else:
                children = []
                try:
                    for child in sorted(path.iterdir()):
                        children.append(build_tree(child, child.name))
                except PermissionError:
                    pass

                return {
                    "name": name,
                    "type": "directory",
                    "children": children,
                    "path": str(path.relative_to(Config.BASE_DIR))
                }

        tree = {
            "name": "data",
            "type": "directory",
            "children": [
                build_tree(Config.RAW_DIR, "raw"),
                build_tree(Config.PROCESSED_DIR, "processed"),
                build_tree(Config.DEBUG_DIR, "debug"),
            ]
        }

        return tree
    except Exception as e:
        logger.error(f"Failed to build storage tree: {e}")
        raise HTTPException(status_code=500, detail=str(e))
