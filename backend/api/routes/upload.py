"""Upload router: file upload for media."""
from __future__ import annotations
import os
import uuid
import time
from fastapi import APIRouter, UploadFile, File, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

router = APIRouter(prefix="/api/uploads", tags=["uploads"])

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_TYPES = {
    "video/mp4", "video/quicktime", "video/x-msvideo", "video/webm",
    "image/jpeg", "image/png", "image/gif", "image/webp",
}

@router.post("/")
async def upload_file(request: Request, file: UploadFile = File(...)):
    """Upload a media file and return its URL."""
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(400, f"File type {file.content_type} not allowed. Use mp4, jpeg, png, etc.")
    
    ext = file.filename.rsplit(".", 1)[-1] if "." in file.filename else "mp4"
    unique_name = f"{uuid.uuid4().hex[:12]}_{int(time.time())}.{ext}"
    file_path = os.path.join(UPLOAD_DIR, unique_name)
    
    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)
    
    file_size = len(content)
    file_url = f"/api/uploads/{unique_name}"
    # Build full URL so frontend accepts it
    host = request.headers.get("host", "localhost:8000")
    full_url = f"http://{host}{file_url}"
    
    return {
        "url": full_url,
        "filename": unique_name,
        "size": file_size,
        "content_type": file.content_type,
        "message": f"Uploaded {file_size} bytes"
    }

@router.get("/{filename}")
async def get_uploaded_file(filename: str):
    """Serve uploaded files."""
    file_path = os.path.join(UPLOAD_DIR, filename)
    if not os.path.exists(file_path):
        raise HTTPException(404, "File not found")
    return FileResponse(file_path)
