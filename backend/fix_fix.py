with open("api/main.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    # Fix import line
    if "upload as upload_routes," in line.lstrip() and not line.startswith("    "):
        lines[i] = "    upload as upload_routes,\n"
        print(f"Fixed import line {i+1}")
    # Fix router line
    if "upload_routes.router" in line and not line.startswith("    "):
        lines[i] = "    app.include_router(upload_routes.router, tags=[\"Uploads\"])\n"
        print(f"Fixed router line {i+1}")

with open("api/main.py", "w", encoding="utf-8") as f:
    f.writelines(lines)
print("Done!")
