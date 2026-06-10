import sqlite3
conn = sqlite3.connect("social_agent.db")
cursor = conn.cursor()
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cursor.fetchall()]
print("Tables:", tables)

# Also find the token for tiktok
for t in tables:
    try:
        cursor.execute(f"SELECT * FROM {t} LIMIT 1")
        cols = [d[0] for d in cursor.description]
        if "access_token" in cols or "token" in cols:
            print(f"\nTable '{t}' has columns: {cols}")
            cursor.execute(f"SELECT * FROM {t} WHERE platform='tiktok' OR LOWER(platform)='tiktok' LIMIT 1")
            row = cursor.fetchone()
            if row:
                print(f"Found tiktok row: {row[:3]}...")
    except Exception as e:
        pass
conn.close()
