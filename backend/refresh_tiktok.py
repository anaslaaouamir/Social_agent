import asyncio
import httpx
import json
import psycopg2

conn = psycopg2.connect("postgresql://agent:agentpass@127.0.0.1:5433/social_agent")
cur = conn.cursor()
cur.execute("SELECT access_token, refresh_token FROM social_accounts WHERE platform='TIKTOK' ORDER BY updated_at DESC LIMIT 1")
row = cur.fetchone()
conn.close()

if not row:
    print("No TikTok account found!")
    exit()

token, refresh = row[0], row[1]
print(f"Access token: {token[:20]}...")
print(f"Refresh token: {str(refresh)[:20] if refresh else 'NONE'}...")
print(f"Refresh token length: {len(refresh) if refresh else 0}")

if not refresh:
    print("\nNo refresh token! Need to re-authenticate.")
    exit()

async def refresh():
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "https://open.tiktokapis.com/v2/oauth/token/",
            data={
                "client_key": "sbaw30wwxe1t1d5bmw",
                "client_secret": "Y5eLUtzlV1pY11u4FK8va8Hswx7vlE8z",
                "grant_type": "refresh_token",
                "refresh_token": refresh,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        print(f"\nStatus: {resp.status_code}")
        data = resp.json()
        print(f"Response: {json.dumps(data, indent=2)}")
        
        if "access_token" in data:
            conn2 = psycopg2.connect("postgresql://agent:agentpass@127.0.0.1:5433/social_agent")
            cur2 = conn2.cursor()
            cur2.execute("UPDATE social_accounts SET access_token = %s, refresh_token = %s WHERE platform = 'TIKTOK'", 
                        (data["access_token"], data.get("refresh_token", refresh)))
            conn2.commit()
            conn2.close()
            print("\nToken updated in database!")

asyncio.run(refresh())
