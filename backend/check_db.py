import sqlite3
import os

# Check if file exists
print("social_agent.db exists:", os.path.exists("social_agent.db"))
print("DB files in dir:")
for f in os.listdir("."):
    if f.endswith(".db") or "social" in f.lower():
        print(f"  {f} ({os.path.getsize(f)} bytes)")
