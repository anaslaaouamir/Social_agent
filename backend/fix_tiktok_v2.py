with open("services/social_publisher.py", "r", encoding="utf-8") as f:
    content = f.read()

# Fix: Download video FIRST to get size, then add video_size to init request
old_code = '''        try:
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
            logger.info(f"Downloaded video: {len(video_bytes)} bytes")'''

new_code = '''        try:
            # Step 1: Download the video first to get its size
            prepared_url = await self._prepare_non_facebook_media_url(
                "tiktok",
                media_urls[0],
                post_id=source_post_id,
                media_index=0,
            )
            video_resp = await self._client.get(prepared_url, follow_redirects=True)
            video_resp.raise_for_status()
            video_bytes = video_resp.content
            video_size = len(video_bytes)
            logger.info(f"Downloaded video: {video_size} bytes")

            # Step 2: Init with PUSH_TO_URL - TikTok gives us an upload URL
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
                        "video_size": video_size,
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
                return self._failed_result("tiktok", error_msg)'''

if old_code in content:
    content = content.replace(old_code, new_code)
    print("SUCCESS: Fixed - download first, then init with video_size")
else:
    print("ERROR: Could not find the code to replace!")
    # Show surrounding context for debugging
    idx = content.find("PUSH_TO_URL")
    if idx >= 0:
        print(f"Found PUSH_TO_URL at index {idx}")
        print(content[idx-200:idx+500])

with open("services/social_publisher.py", "w", encoding="utf-8") as f:
    f.write(content)
