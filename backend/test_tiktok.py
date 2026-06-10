import asyncio
import httpx
import json
import psycopg2

conn = psycopg2.connect("postgresql://agent:agentpass@127.0.0.1:5433/social_agent")
cur = conn.cursor()
cur.execute("SELECT access_token FROM social_accounts WHERE platform='TIKTOK' ORDER BY updated_at DESC LIMIT 1")
row = cur.fetchone()
conn.close()

if not row:
    print("No TikTok token found!")
    exit()

token = row[0]
print(f"Token found: {token[:30]}...")

async def test():
    async with httpx.AsyncClient() as client:
        print("\n=== Testing TikTok Content Posting API ===")
        resp = await client.post(
            "https://open.tiktokapis.com/v2/post/publish/video/init/",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "post_info": {
                    "title": "Test post",
                    "disable_comment": False,
                    "privacy_level": "PUBLIC_TO_EVERYONE",
                },
                "source_info": {
                    "source": "PULL_FROM_URL",
                    "video_url": "https://www.w3schools.com/html/mov_bbb.mp4",
                },
            },
        )
        print(f"Status: {resp.status_code}")
        print(f"Response: {json.dumps(resp.json(), indent=2)}")

asyncio.run(test())
