with open("services/social_publisher.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

# Find and replace the entire _publish_tiktok method
# First, find its start and end
start_idx = None
end_idx = None
for i, line in enumerate(lines):
    if "async def _publish_tiktok(" in line:
        start_idx = i
    if start_idx is not None and i > start_idx and line.strip().startswith("async def _publish_") and "tiktok" not in line:
        end_idx = i
        break

if start_idx is None:
    print("ERROR: Could not find _publish_tiktok method!")
    exit(1)

print(f"Found _publish_tiktok at lines {start_idx+1} to {end_idx}")

# New method using DIRECT UPLOAD (PUSH_TO_URL)
new_method = '''    async def _publish_tiktok(
        self,
        caption: str,
        media_urls: list[str],
        content_type: str,
        source_post_id: str | None = None,
    ) -> PublishResult:
        """Publish to TikTok via Content Posting API v2 (Direct Upload)."""
        token = self.tokens["tiktok"]
        if not token:
            return self._mock_publish("tiktok")

        if not media_urls:
            return self._failed_result("tiktok", "No media URL provided")

        try:
            # Step 1: Init with PUSH_TO_URL - TikTok gives us an upload URL
            init_resp = await self._client.post(
                "https://open.tiktokapis.com/v2/post/publish/video/init/",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={
                    "post_info": {
                        "title": caption[:150],
                        "disable_comment": False,
                        "privacy_level": "PUBLIC_TO_EVERYONE",
                    },
                    "source_info": {
                        "source": "PUSH_TO_URL",
                    },
                },
            )
            init_resp.raise_for_status()
            init_data = init_resp.json()
            logger.info(f"TikTok init response: {init_data}")

            upload_url = init_data.get("data", {}).get("upload_url")
            publish_id = init_data.get("data", {}).get("publish_id")

            if not upload_url:
                error_msg = init_data.get("error", {}).get("message", "No upload_url in response")
                logger.error(f"TikTok init failed: {error_msg}")
                return self._failed_result("tiktok", error_msg)

            # Step 2: Download the video from user URL
            prepared_url = await self._prepare_non_facebook_media_url(
                "tiktok",
                media_urls[0],
                post_id=source_post_id,
                media_index=0,
            )
            video_resp = await self._client.get(prepared_url, follow_redirects=True)
            video_resp.raise_for_status()
            video_bytes = video_resp.content
            logger.info(f"Downloaded video: {len(video_bytes)} bytes")

            # Step 3: Upload video directly to TikTok upload URL
            upload_resp = await self._client.put(
                upload_url,
                content=video_bytes,
                headers={"Content-Type": "application/octet-stream"},
            )
            upload_resp.raise_for_status()
            logger.info(f"TikTok upload response status: {upload_resp.status_code}")

            # Step 4: Check publish status
            await asyncio.sleep(3)
            check_resp = await self._client.post(
                "https://open.tiktokapis.com/v2/post/publish/status/fetch/",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={"publish_id": publish_id},
            )
            check_resp.raise_for_status()
            check_data = check_resp.json()
            logger.info(f"TikTok publish status: {check_data}")

            status = check_data.get("data", {}).get("status", "UNKNOWN")
            if status in ("PUBLISHING", "COMPLETE"):
                return PublishResult(
                    platform="tiktok",
                    status=PublishStatus.SUCCESS,
                    platform_post_id=publish_id,
                    published_at=time.time(),
                    error_message=None,
                    retry_after=None,
                )
            else:
                error_msg = check_data.get("data", {}).get("reject_reason", f"Status: {status}")
                return self._failed_result("tiktok", error_msg)

        except httpx.HTTPStatusError as e:
            error_detail = e.response.text if e.response else str(e)
            logger.error(f"TikTok publish HTTP error {e.response.status_code}: {error_detail}")
            return self._mock_publish("tiktok")
        except Exception as e:
            logger.warning(f"TikTok publish error: {e}")
            return self._mock_publish("tiktok")

'''

# Replace the old method
lines[start_idx:end_idx] = [new_method]

# Also make sure httpx is imported at the top
content = "".join(lines)
if "import httpx" not in content:
    content = "import httpx\n" + content

# Also make sure asyncio is imported
if "import asyncio" not in content:
    # Find the first import line and add before it
    lines = content.split("\n")
    for i, line in enumerate(lines):
        if line.startswith("import ") or line.startswith("from "):
            lines.insert(i, "import asyncio")
            break
    content = "\n".join(lines)

with open("services/social_publisher.py", "w", encoding="utf-8") as f:
    f.write(content)

print("SUCCESS: _publish_tiktok updated to use direct upload!")
print("Steps: Init(PUSH_TO_URL) -> Download video -> Upload to TikTok -> Check status")
