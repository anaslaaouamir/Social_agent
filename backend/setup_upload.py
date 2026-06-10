import os

backend = r"C:\Users\sys\Social_agent\backend"
frontend_src = r"C:\Users\sys\Social_agent\frontend\src"

# 1. Create uploads directory
uploads_dir = os.path.join(backend, "uploads")
os.makedirs(uploads_dir, exist_ok=True)
print(f"Created: {uploads_dir}")

# 2. Create upload route
upload_route = '''"""Upload router: file upload for media."""
from __future__ import annotations
import os
import uuid
import time
from fastapi import APIRouter, UploadFile, File, HTTPException
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
async def upload_file(file: UploadFile = File(...)):
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
    
    return {
        "url": file_url,
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
'''

upload_path = os.path.join(backend, "api", "routes", "upload.py")
with open(upload_path, "w", encoding="utf-8") as f:
    f.write(upload_route)
print(f"Created: {upload_path}")

# 3. Register upload route in main.py
main_path = os.path.join(backend, "api", "main.py")
with open(main_path, "r", encoding="utf-8") as f:
    main_content = f.read()

if "upload" not in main_content:
    # Add import
    main_content = main_content.replace(
        "from api.routes import (",
        "from api.routes import (\n    upload as upload_routes,"
    )
    # Add router - find where other routers are included
    main_content = main_content.replace(
        "app.include_router(tiktok_oauth.router)",
        "app.include_router(tiktok_oauth.router)\n    app.include_router(upload_routes.router)"
    )

with open(main_path, "w", encoding="utf-8") as f:
    f.write(main_content)
print(f"Updated: {main_path}")

print("\n=== Backend done ===")
print("Upload endpoint: POST /api/uploads/")
print("Serve files: GET /api/uploads/{filename}")
