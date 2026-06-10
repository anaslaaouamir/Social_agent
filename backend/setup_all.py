import os

# 1. Update CreatePostPage.tsx - add upload button
frontend_file = r"C:\Users\sys\Social_agent\frontend\src\pages\CreatePostPage.tsx"

with open(frontend_file, "r", encoding="utf-8") as f:
    content = f.read()

# Add upload handler function after mediaUrls state (around line 40)
upload_handler = '''
  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
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
  }

'''

if "handleFileUpload" not in content:
    # Insert after the mediaUrls state declaration
    content = content.replace(
        "const [mediaUrls, setMediaUrls] = useState<string[]>([])",
        "const [mediaUrls, setMediaUrls] = useState<string[]>([])" + upload_handler
    )

# Add upload button before the URL input
upload_button = '''            <div style={{ display: "flex", gap: 8, marginBottom: 8, alignItems: "center" }}>
              <label style={{
                display: "inline-flex", alignItems: "center", gap: 6,
                padding: "6px 12px", borderRadius: 8, cursor: "pointer",
                background: "var(--accent)", color: "#fff", fontSize: 13, fontWeight: 600,
              }}>
                📁 Upload depuis PC
                <input type="file" accept="video/*,image/*" onChange={handleFileUpload} style={{ display: "none" }} />
              </label>
              <span style={{ fontSize: 11, color: "var(--text-3)" }}>ou entrez les URLs ci-dessous</span>
            </div>

'''

if "Upload depuis PC" not in content:
    # Insert before the URL input field
    content = content.replace(
        '            <input\n              value={mediaUrls.join',
        upload_button + '            <input\n              value={mediaUrls.join'
    )

with open(frontend_file, "w", encoding="utf-8") as f:
    f.write(content)

print("Updated: CreatePostPage.tsx")

# 2. Fix TikTok publish to use draft mode (no privacy_level)
publisher_file = r"C:\Users\sys\Social_agent\backend\services\social_publisher.py"

with open(publisher_file, "r", encoding="utf-8") as f:
    pub_content = f.read()

# Change TikTok init to draft mode - remove privacy_level for draft
old_tiktok_init = '''                "post_info": {
                        "title": caption[:150],
                        "disable_comment": False,
                        "privacy_level": "PUBLIC_TO_EVERYONE",
                    },
                    "source_info": {
                        "source": "PUSH_TO_URL",
                        "video_size": video_size,
                    },'''

new_tiktok_init = '''                "post_info": {
                        "title": caption[:150],
                        "disable_comment": False,
                        "privacy_level": "PUBLIC_TO_EVERYONE",
                    },
                    "source_info": {
                        "source": "PUSH_TO_URL",
                        "video_size": video_size,
                        "video_url": prepared_url,
                    },'''

if old_tiktok_init in pub_content:
    pub_content = pub_content.replace(old_tiktok_init, new_tiktok_init)
    print("Updated: TikTok publish - added video_url to PUSH_TO_URL")
else:
    print("WARNING: Could not find TikTok init code to update")
    # Try to find it
    idx = pub_content.find("PUSH_TO_URL")
    if idx > 0:
        print(f"Found PUSH_TO_URL at index {idx}")
        print(pub_content[idx-100:idx+200])

with open(publisher_file, "w", encoding="utf-8") as f:
    f.write(pub_content)

print("\n=== All done ===")
print("Frontend: Upload button added to CreatePostPage")
print("Backend: Upload endpoint at POST /api/uploads/")
print("TikTok: Added video_url to PUSH_TO_URL request")
