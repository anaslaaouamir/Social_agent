with open("api/main.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "upload_routes.router" in line and "IndentationError" not in line:
        print(f"Line {i+1}: {repr(line)}")

