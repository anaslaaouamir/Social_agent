with open("api/main.py", "r", encoding="utf-8") as f:
    content = f.read()

# Fix: ensure proper indentation (4 spaces like other lines)
content = content.replace(
    'app.include_router(upload_routes.router, tags=["Uploads"])\n',
    'app.include_router(upload_routes.router, tags=["Uploads"])\n'
)

# The issue is likely the newline spacing. Find and show context
lines = content.split("\n")
for i, line in enumerate(lines):
    if "upload_routes" in line:
        print(f"Line {i+1}: '{line}'")
        # Fix: match indentation of the line above
        if i > 0:
            prev_indent = len(lines[i-1]) - len(lines[i-1].lstrip())
            current_indent = len(line) - len(line.lstrip())
            if current_indent != prev_indent:
                fixed_line = " " * prev_indent + line.lstrip()
                lines[i] = fixed_line
                print(f"Fixed to: '{fixed_line}'")

content = "\n".join(lines)
with open("api/main.py", "w", encoding="utf-8") as f:
    f.write(content)
print("Done!")
