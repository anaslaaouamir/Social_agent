with open("api/main.py", "r", encoding="utf-8") as f:
    content = f.read()

if "upload_routes.router" not in content:
    content = content.replace(
        'app.include_router(meta_webhooks.router, prefix="/api/webhooks", tags=["Meta Webhooks"])',
        'app.include_router(meta_webhooks.router, prefix="/api/webhooks", tags=["Meta Webhooks"])\n    app.include_router(upload_routes.router, tags=["Uploads"])'
    )
    with open("api/main.py", "w", encoding="utf-8") as f:
        f.write(content)
    print("Added: app.include_router(upload_routes.router)")
else:
    print("Already present")
