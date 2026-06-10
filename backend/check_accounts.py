import psycopg2
conn = psycopg2.connect("postgresql://agent:agentpass@127.0.0.1:5433/social_agent")
cur = conn.cursor()
cur.execute("SELECT platform, account_name, account_id, LEFT(access_token, 20) as token_start FROM social_accounts ORDER BY updated_at DESC LIMIT 10")
rows = cur.fetchall()
for r in rows:
    print(f"  {r[0]}: {r[1]} (id: {r[2]}, token: {r[3]})")
conn.close()
