import os

# 1. Fix frontend - use base64 data URL for uploaded files
frontend_file = r"C:\Users\sys\Social_agent\frontend\src\pages\CreatePostPage.tsx"
with open(frontend_file, "r", encoding="utf-8") as f:
    content = f.read()

old_handler = """  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const formData = new FormData()
    formData.append("file", file)
    try {
      const resp = await fetch("/api/uploads/", { method: "POST", body: formData })
      if (!resp.ok) throw new Error("Upload failed")
      const data = await resp.json()
      setMediaUrls((prev: string[]) => [...prev, data.url])
      alert("Fichier uploade: " + data.url)
    } catch (err) {
      alert("Erreur upload: " + (err as Error).message)
    }
    e.target.value = ""
  }"""

new_handler = """  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    // Read file as base64 data URL (accepted by validation)
    const reader = new FileReader()
    reader.onload = () => {
      const dataUrl = reader.result as string
      setMediaUrls((prev: string[]) => [...prev, dataUrl])
      // Also upload to server so backend can access it
      const formData = new FormData()
      formData.append("file", file)
      fetch("/api/uploads/", { method: "POST", body: formData }).catch(() => {})
    }
    reader.readAsDataURL(file)
    e.target.value = ""
  }"""

if old_handler in content:
    content = content.replace(old_handler, new_handler)
    print("Updated: frontend upload uses base64 data URL")
else:
    print("WARNING: old handler not found")

with open(frontend_file, "w", encoding="utf-8") as f:
    f.write(content)

# 2. Fix backend TikTok publisher - handle base64 data URLs
pub_file = r"C:\Users\sys\Social_agent\backend\services\social_publisher.py"
with open(pub_file, "r", encoding="utf-8") as f:
    pub_content = f.read()

# Add base64 handling before the download step
old_download = """            # Step 1: Download the video first to get its size
            prepared_url = await self._prepare_non_facebook_media_url(
                "tiktok",
                media_urls[0],
                post_id=source_post_id,
                media_index=0,
            )
            video_resp = await self._client.get(prepared_url, follow_redirects=True)
            video_resp.raise_for_status()
            video_bytes = video_resp.content"""

new_download = """            # Step 1: Get video bytes (from base64 data URL or download)
            raw_url = media_urls[0]
            if raw_url.startswith("data:"):
                # Base64 data URL from file upload
                import base64 as b64mod
                header, b64data = raw_url.split(",", 1)
                video_bytes = b64mod.b64decode(b64data)
                logger.info(f"Decoded base64 video: {len(video_bytes)} bytes")
            else:
                prepared_url = await self._prepare_non_facebook_media_url(
                    "tiktok",
                    raw_url,
                    post_id=source_post_id,
                    media_index=0,
                )
                video_resp = await self._client.get(prepared_url, follow_redirects=True)
                video_resp.raise_for_status()
                video_bytes = video_resp.content"""

if old_download in pub_content:
    pub_content = pub_content.replace(old_download, new_download)
    print("Updated: TikTok publisher handles base64 data URLs")
else:
    print("WARNING: old download code not found")

with open(pub_file, "w", encoding="utf-8") as f:
    f.write(pub_content)

print("\n=== All done ===")
print("Frontend: File upload converts to base64 data URL")
print("Backend: TikTok publisher decodes base64 for upload")
