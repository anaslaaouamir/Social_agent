import asyncio
import httpx
import json
import psycopg2

conn = psycopg2.connect("postgresql://agent:agentpass@127.0.0.1:5433/social_agent")
cur = conn.cursor()
cur.execute("SELECT access_token FROM social_accounts WHERE platform='TIKTOK' ORDER BY updated_at DESC LIMIT 1")
row = cur.fetchone()
conn.close()
token = row[0]
print(f"Token: {token[:20]}...")

async def test():
    async with httpx.AsyncClient() as client:
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        # Test 1: PUSH_TO_URL with video_size
        print("\n=== Test 1: PUSH_TO_URL ===")
        resp = await client.post(
            "https://open.tiktokapis.com/v2/post/publish/video/init/",
            headers=headers,
            json={
                "post_info": {"title": "Test", "disable_comment": False, "privacy_level": "PUBLIC_TO_EVERYONE"},
                "source_info": {"source": "PUSH_TO_URL", "video_size": 411598},
            },
        )
        print(f"Status: {resp.status_code}")
        print(f"Response: {json.dumps(resp.json(), indent=2)}")

        # Test 2: PULL_FROM_URL with the verified approach
        print("\n=== Test 2: PULL_FROM_URL ===")
        resp2 = await client.post(
            "https://open.tiktokapis.com/v2/post/publish/video/init/",
            headers=headers,
            json={
                "post_info": {"title": "Test", "disable_comment": False, "privacy_level": "PUBLIC_TO_EVERYONE"},
                "source_info": {"source": "PULL_FROM_URL", "video_url": "https://www.w3schools.com/html/mov_bbb.mp4"},
            },
        )
        print(f"Status: {resp2.status_code}")
        print(f"Response: {json.dumps(resp2.json(), indent=2)}")

asyncio.run(test())
