import os

# 1. Fix TikTok - add post_mode DRAFT_ONLY and proper source_info
pub_file = r"C:\Users\sys\Social_agent\backend\services\social_publisher.py"
with open(pub_file, "r", encoding="utf-8") as f:
    content = f.read()

# Find the TikTok init section and replace
old = '''            # Step 2: Init with PUSH_TO_URL - TikTok gives us an upload URL
            payload = {
                "post_info": {
                    "title": caption[:150],
                    "privacy_level": "PUBLIC_TO_EVERYONE"'''

new = '''            # Step 2: Init with PUSH_TO_URL - TikTok gives us an upload URL
            # Use DRAFT_ONLY mode (enabled by default in sandbox)
            payload = {
                "post_info": {
                    "title": caption[:150],
                    "privacy_level": "PUBLIC_TO_EVERYONE",
                    "post_mode": "DRAFT_ONLY"'''

if old in content:
    content = content.replace(old, new)
    print("Updated: Added post_mode DRAFT_ONLY")
else:
    print("WARNING: exact match not found, trying alternative...")
    # Find and show context
    idx = content.find('"title": caption[:150]')
    if idx > 0:
        print(f"Found title at index {idx}")
        print(repr(content[idx:idx+300]))

with open(pub_file, "w", encoding="utf-8") as f:
    f.write(content)

print("Done!")
