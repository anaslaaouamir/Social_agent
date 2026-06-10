with open("api/routes/upload.py", "r", encoding="utf-8") as f:
    content = f.read()

# Change to return full URL and read file bytes for TikTok
content = content.replace(
    'from fastapi import APIRouter, UploadFile, File, HTTPException',
    'from fastapi import APIRouter, UploadFile, File, HTTPException, Request'
)

content = content.replace(
    'async def upload_file(file: UploadFile = File(...)):',
    'async def upload_file(request: Request, file: UploadFile = File(...)):'
)

content = content.replace(
    '''    file_url = f"/api/uploads/{unique_name}"
    
    return {
        "url": file_url,''',
    '''    file_url = f"/api/uploads/{unique_name}"
    # Build full URL so frontend accepts it
    host = request.headers.get("host", "localhost:8000")
    full_url = f"http://{host}{file_url}"
    
    return {
        "url": full_url,'''
)

with open("api/routes/upload.py", "w", encoding="utf-8") as f:
    f.write(content)
print("Fixed: upload returns full URL")
