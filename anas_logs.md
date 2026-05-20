# Local Environment Fixes

## 1. Updated `backend/Dockerfile`
- **Change:** Modified `RUN pip install --no-cache-dir -r requirements.txt` to `RUN pip install --default-timeout=1000 --no-cache-dir -r requirements.txt`.
- **Reason:** The `backend/requirements.txt` was updated in the final version (e.g., adding `langgraph`), meaning Docker has to re-install all packages from scratch. The 1000s timeout ensures large libraries like `torch` and `xgboost` do not fail due to network drops during this fresh build.

## 2. Configured `.env` File
- **Change:** Created the `.env` file based on the final version's `.env.example`, and formatted `ALLOWED_HOSTS` as a JSON array (`ALLOWED_HOSTS=["localhost", "127.0.0.1"]`).
- **Reason:** Pydantic (`pydantic_settings`) parses `list[str]` fields strictly as JSON arrays when injected via Docker Compose. Passing a raw comma-separated string causes the backend container to crash loop. Since you hadn't filled in specific real keys yet, using the final version's `.env.example` ensures newer variables (like `HUGGING_FACE_API`) are properly included.
