with open("api/main.py", "r", encoding="utf-8") as f:
    content = f.read()

content = content.replace(
    '    app.include_router(upload_routes.router, tags=["Uploads"])\n',
    'app.include_router(upload_routes.router, tags=["Uploads"])\n'
)

with open("api/main.py", "w", encoding="utf-8") as f:
    f.write(content)
print("Fixed!")
