import re

with open('services/social_publisher.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find and fix the broken section around line 220
new_lines = []
skip_next = False
for i, line in enumerate(lines):
    line_num = i + 1
    if skip_next:
        skip_next = False
        continue
    # Skip the broken logger.error line we added
    if 'TikTok publish detail:' in line or 'TikTok 403 detail:' in line or 'TikTok API error detail:' in line:
        continue
    new_lines.append(line)

with open('services/social_publisher.py', 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print('Fixed! Removed broken lines.')
