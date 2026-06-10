import psycopg2
conn = psycopg2.connect("postgresql://agent:agentpass@127.0.0.1:5433/social_agent")
cur = conn.cursor()
cur.execute("SELECT unnest(enum_range(NULL::platform))")
enums = [r[0] for r in cur.fetchall()]
print("Platform enum values:", enums)

cur.execute("SELECT platform, account_name, LEFT(access_token, 20) as token_start FROM social_accounts LIMIT 10")
rows = cur.fetchall()
for r in rows:
    print(f"  {r[0]}: {r[1]} (token: {r[2]}...)")
conn.close()
