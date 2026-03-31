from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from typing import List, Optional
from pydantic import BaseModel
import os
import shutil
from datetime import datetime
import json
from pathlib import Path
from config import Config

router = APIRouter(prefix="/api/drive", tags=["drive"])

# Models
class FolderCreate(BaseModel):
    name: str
    parent_path: str = ""

class FileMove(BaseModel):
    source_paths: List[str]
    destination_path: str

class FileCopy(BaseModel):
    source_paths: List[str]
    destination_path: str

class FileDelete(BaseModel):
    paths: List[str]

class PDFMerge(BaseModel):
    file_paths: List[str]
    output_name: str

class PDFSplit(BaseModel):
    file_path: str
    page_ranges: List[tuple]  # [(1, 5), (6, 10)]

# Helper functions
def get_drive_root():
    """Get the root directory for user drive"""
    drive_root = os.path.join(Config.DATA_DIR, "drive")
    os.makedirs(drive_root, exist_ok=True)
    return drive_root

def get_full_path(relative_path: str):
    """Convert relative path to full path"""
    drive_root = get_drive_root()
    if relative_path:
        full_path = os.path.join(drive_root, relative_path.lstrip("/"))
    else:
        full_path = drive_root
    return os.path.normpath(full_path)

def get_file_info(file_path: str, relative_path: str):
    """Get file/folder information"""
    stat = os.stat(file_path)
    is_dir = os.path.isdir(file_path)

    return {
        "name": os.path.basename(file_path),
        "path": relative_path,
        "type": "folder" if is_dir else "file",
        "size": stat.st_size if not is_dir else 0,
        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        "is_ocr_processed": False if is_dir else file_path.endswith(".pdf"),
    }

def list_directory(path: str = ""):
    """List all files and folders in a directory"""
    full_path = get_full_path(path)

    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="Directory not found")

    items = []

    try:
        for entry in os.scandir(full_path):
            relative = os.path.join(path, entry.name) if path else entry.name
            items.append(get_file_info(entry.path, relative))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list directory: {str(e)}")

    # Sort: folders first, then files
    items.sort(key=lambda x: (x["type"] != "folder", x["name"].lower()))

    return items

# API Endpoints
@router.get("/list")
async def list_files(path: str = ""):
    """List all files and folders in the specified path"""
    return {
        "path": path,
        "items": list_directory(path)
    }

@router.post("/folder")
async def create_folder(folder: FolderCreate):
    """Create a new folder"""
    full_path = get_full_path(os.path.join(folder.parent_path, folder.name))

    if os.path.exists(full_path):
        raise HTTPException(status_code=400, detail="Folder already exists")

    try:
        os.makedirs(full_path, exist_ok=True)
        relative_path = os.path.join(folder.parent_path, folder.name) if folder.parent_path else folder.name
        return {
            "message": "Folder created successfully",
            "folder": get_file_info(full_path, relative_path)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create folder: {str(e)}")

@router.post("/upload")
async def upload_files(
    files: List[UploadFile] = File(...),
    path: str = ""
):
    """Upload multiple files to the specified path"""
    full_path = get_full_path(path)

    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="Destination folder not found")

    uploaded_files = []

    for file in files:
        try:
            file_path = os.path.join(full_path, file.filename)

            # Save file
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

            relative_path = os.path.join(path, file.filename) if path else file.filename
            uploaded_files.append(get_file_info(file_path, relative_path))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to upload {file.filename}: {str(e)}")

    return {
        "message": f"{len(uploaded_files)} file(s) uploaded successfully",
        "files": uploaded_files
    }

@router.post("/move")
async def move_files(move: FileMove):
    """Move files/folders to another location"""
    dest_full = get_full_path(move.destination_path)

    if not os.path.exists(dest_full):
        raise HTTPException(status_code=404, detail="Destination folder not found")

    moved_items = []

    for source_path in move.source_paths:
        source_full = get_full_path(source_path)

        if not os.path.exists(source_full):
            continue

        name = os.path.basename(source_full)
        dest_item = os.path.join(dest_full, name)

        try:
            shutil.move(source_full, dest_item)
            relative_path = os.path.join(move.destination_path, name) if move.destination_path else name
            moved_items.append(relative_path)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to move {source_path}: {str(e)}")

    return {
        "message": f"{len(moved_items)} item(s) moved successfully",
        "items": moved_items
    }

@router.post("/copy")
async def copy_files(copy: FileCopy):
    """Copy files/folders to another location"""
    dest_full = get_full_path(copy.destination_path)

    if not os.path.exists(dest_full):
        raise HTTPException(status_code=404, detail="Destination folder not found")

    copied_items = []

    for source_path in copy.source_paths:
        source_full = get_full_path(source_path)

        if not os.path.exists(source_full):
            continue

        name = os.path.basename(source_full)
        dest_item = os.path.join(dest_full, name)

        try:
            if os.path.isdir(source_full):
                shutil.copytree(source_full, dest_item)
            else:
                shutil.copy2(source_full, dest_item)

            relative_path = os.path.join(copy.destination_path, name) if copy.destination_path else name
            copied_items.append(relative_path)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to copy {source_path}: {str(e)}")

    return {
        "message": f"{len(copied_items)} item(s) copied successfully",
        "items": copied_items
    }

@router.post("/delete")
async def delete_files(delete: FileDelete):
    """Delete files/folders"""
    deleted_items = []

    for path in delete.paths:
        full_path = get_full_path(path)

        if not os.path.exists(full_path):
            continue

        try:
            if os.path.isdir(full_path):
                shutil.rmtree(full_path)
            else:
                os.remove(full_path)

            deleted_items.append(path)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to delete {path}: {str(e)}")

    return {
        "message": f"{len(deleted_items)} item(s) deleted successfully",
        "items": deleted_items
    }

@router.post("/merge-pdfs")
async def merge_pdfs(merge: PDFMerge):
    """Merge multiple PDF files"""
    try:
        from PyPDF2 import PdfMerger

        merger = PdfMerger()

        for file_path in merge.file_paths:
            full_path = get_full_path(file_path)

            if not os.path.exists(full_path) or not full_path.endswith('.pdf'):
                continue

            merger.append(full_path)

        # Save merged PDF
        output_dir = get_full_path("")
        output_path = os.path.join(output_dir, merge.output_name)

        if not output_path.endswith('.pdf'):
            output_path += '.pdf'

        merger.write(output_path)
        merger.close()

        relative_path = os.path.basename(output_path)

        return {
            "message": "PDFs merged successfully",
            "file": get_file_info(output_path, relative_path)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to merge PDFs: {str(e)}")

@router.get("/download")
async def download_file(path: str):
    """Download a file from the drive"""
    full_path = get_full_path(path)

    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="File not found")

    if os.path.isdir(full_path):
        raise HTTPException(status_code=400, detail="Cannot download a folder")

    return FileResponse(
        path=full_path,
        filename=os.path.basename(full_path),
        media_type="application/octet-stream"
    )


@router.post("/split-pdf")
async def split_pdf(split: PDFSplit):
    """Split a PDF file into multiple parts"""
    try:
        from PyPDF2 import PdfReader, PdfWriter

        full_path = get_full_path(split.file_path)

        if not os.path.exists(full_path):
            raise HTTPException(status_code=404, detail="PDF file not found")

        reader = PdfReader(full_path)
        base_name = os.path.splitext(os.path.basename(full_path))[0]
        output_dir = os.path.dirname(full_path)

        split_files = []

        for idx, (start, end) in enumerate(split.page_ranges, 1):
            writer = PdfWriter()

            for page_num in range(start - 1, end):
                if page_num < len(reader.pages):
                    writer.add_page(reader.pages[page_num])

            output_name = f"{base_name}_part{idx}.pdf"
            output_path = os.path.join(output_dir, output_name)

            with open(output_path, "wb") as output_file:
                writer.write(output_file)

            relative_path = os.path.join(os.path.dirname(split.file_path), output_name) if os.path.dirname(split.file_path) else output_name
            split_files.append(get_file_info(output_path, relative_path))

        return {
            "message": f"PDF split into {len(split_files)} parts",
            "files": split_files
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to split PDF: {str(e)}")
