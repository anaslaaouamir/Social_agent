with open("services/social_publisher.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

if lines[368].strip() == "resp.raise_for_status()":
    lines[368] = "                    resp.raise_for_status()\n"
    print("Fixed line 369")

for i, line in enumerate(lines):
    if "except Exception as e:" in line and i > 490 and i < 510:
        if i+1 < len(lines) and 'self._mock_publish("tiktok")' in lines[i+1]:
            indent = "        "
            insert_lines = [
                f"{indent}except httpx.HTTPStatusError as e:\n",
                f"{indent}    error_detail = e.response.text if e.response else str(e)\n",
                f'{indent}    logger.error(f"TikTok publish HTTP error {{e.response.status_code}}: {{error_detail}}")\n',
                f'{indent}    return self._mock_publish("tiktok")\n',
            ]
            lines = lines[:i] + insert_lines + lines[i:]
            print(f"Added HTTP error logging at line {i+1}")
            break

with open("services/social_publisher.py", "w", encoding="utf-8") as f:
    f.writelines(lines)
print("Done!")
