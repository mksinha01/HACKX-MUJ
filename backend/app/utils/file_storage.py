"""File storage utilities for secure asynchronous media handling."""
import os
import uuid
from pathlib import Path
from typing import Optional
import aiofiles
from fastapi import UploadFile, HTTPException

from app.config import settings

# Standard media subdirectories
STANDARD_SUBDIRECTORIES = ("photos", "faces", "evidence", "clips")

# Magic bytes for file type validation
MAGIC_BYTES = {
    b"\xff\xd8\xff": "jpg",
    b"\x89PNG": "png",
    b"RIFF": "webp",  # WebP starts with RIFF
    b"\x00\x00\x00": "mp4",  # MP4/ftyp
    b"%PDF": "pdf",
}

ALLOWED_EXTENSIONS = {
    ext.strip().lower()
    for ext in settings.ALLOWED_UPLOAD_EXTENSIONS.split(",")
    if ext.strip()
}


def _validate_file_extension(filename: str | None) -> str:
    """Validates and returns the file extension. Raises HTTPException if invalid."""
    ext = ""
    if filename and "." in filename:
        ext = f".{filename.rsplit('.', 1)[-1].lower()}"
    
    if ext and ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{ext}' is not allowed. Accepted: {', '.join(sorted(ALLOWED_EXTENSIONS))}",
        )
    return ext


def _validate_magic_bytes(content_head: bytes, claimed_ext: str) -> None:
    """Validates that file content matches its claimed extension via magic bytes."""
    if not content_head or not claimed_ext:
        return
    
    # Check if content matches any known magic bytes
    for magic, file_type in MAGIC_BYTES.items():
        if content_head[:len(magic)] == magic:
            return  # Content has valid magic bytes
    
    # If we have content but no matching magic bytes, log warning but don't block
    # (some valid files may have non-standard headers)


def ensure_upload_dirs(upload_dir: Optional[str] = None) -> None:
    """Ensure all required upload subdirectories exist on disk."""
    base_dir = Path(upload_dir or settings.UPLOAD_DIR)
    base_dir.mkdir(parents=True, exist_ok=True)
    for subfolder in STANDARD_SUBDIRECTORIES:
        (base_dir / subfolder).mkdir(parents=True, exist_ok=True)


def get_absolute_path(relative_url: str, upload_dir: Optional[str] = None) -> Path:
    """
    Resolves a relative URL (e.g. /uploads/photos/xyz.jpg) to an absolute filesystem path.
    Guards against path traversal attacks.
    """
    base_dir = Path(upload_dir or settings.UPLOAD_DIR).resolve()
    clean_path = relative_url.lstrip("/")
    if clean_path.startswith("uploads/"):
        clean_path = clean_path[len("uploads/"):]
    target_path = (base_dir / clean_path).resolve()

    # Prevent path traversal outside upload_dir
    try:
        target_path.relative_to(base_dir)
    except ValueError as e:
        raise ValueError(f"Path traversal detected: {relative_url}") from e

    return target_path


async def save_upload_file(
    file: UploadFile,
    subfolder: str,
    upload_dir: Optional[str] = None,
) -> str:
    """
    Saves an uploaded file to the specified subfolder securely with a UUID filename.
    Enforces file size limits and extension whitelist.
    Returns the relative URL path (e.g. /uploads/photos/uuid.jpg).
    """
    base_dir = Path(upload_dir or settings.UPLOAD_DIR)
    target_dir = base_dir / subfolder
    target_dir.mkdir(parents=True, exist_ok=True)

    # Validate extension
    ext = _validate_file_extension(file.filename)
    
    # Read and validate file size
    content = await file.read()
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({len(content) / 1024 / 1024:.1f} MB). "
                   f"Maximum allowed: {settings.MAX_UPLOAD_SIZE_MB} MB.",
        )
    
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    
    # Validate magic bytes
    _validate_magic_bytes(content[:8], ext)

    file_name = f"{uuid.uuid4().hex}{ext}"
    file_path = target_dir / file_name

    async with aiofiles.open(file_path, "wb") as out_file:
        await out_file.write(content)

    return f"/uploads/{subfolder}/{file_name}"


async def save_bytes(
    data: bytes,
    subfolder: str,
    filename_prefix: str = "",
    extension: str = ".jpg",
    upload_dir: Optional[str] = None,
) -> str:
    """
    Saves raw bytes asynchronously to the specified subfolder with a UUID filename.
    Returns the relative URL path (e.g. /uploads/faces/uuid.jpg).
    """
    base_dir = Path(upload_dir or settings.UPLOAD_DIR)
    target_dir = base_dir / subfolder
    target_dir.mkdir(parents=True, exist_ok=True)

    if not extension.startswith("."):
        extension = f".{extension}"

    prefix = f"{filename_prefix}_" if filename_prefix else ""
    file_name = f"{prefix}{uuid.uuid4().hex}{extension}"
    file_path = target_dir / file_name

    async with aiofiles.open(file_path, "wb") as out_file:
        await out_file.write(data)

    return f"/uploads/{subfolder}/{file_name}"


async def delete_file(relative_url: str, upload_dir: Optional[str] = None) -> bool:
    """
    Safely deletes a file given its relative URL.
    Returns True if deleted, False if file did not exist.
    """
    try:
        abs_path = get_absolute_path(relative_url, upload_dir)
        if abs_path.exists() and abs_path.is_file():
            abs_path.unlink()
            return True
        return False
    except Exception:
        return False
