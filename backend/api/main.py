"""
FastAPI main application - Social Agent Platform
All routers, middleware, CORS, WebSocket, startup events.
"""
from __future__ import annotations

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from api.routes import nlp as nlp_routes
from core.config import get_settings
from core.runtime_state import mark_runtime
from api.routes import (
    auth, posts, analytics, hashtags,
    comments, dm, accounts, alerts, calendar, content,
    monitoring, profile, linkedIn_oauth, facebook_oauth,
    instagram_oauth, twitter_oauth, tiktok_oauth, threads_oauth, youtube_oauth, meta_webhooks,
)

from core.runtime_state import mark_runtime, runtime_state

from fastapi.staticfiles import StaticFiles

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown."""
    logger.info("Starting Social Agent Platform...")
    mark_runtime("app", "running", started_at=time.time())

    try:
        from core.database import engine, Base
        from models.domain import (
            User, SocialAccount, Post, Comment,
            DirectMessage, LLMMemoryEntry, HashtagPerformance, Alert, AccountMetric,
        )
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database tables created/verified")
        mark_runtime("database", "healthy")
    except Exception as exc:
        logger.warning(f"DB init skipped: {exc}")
        mark_runtime("database", "unhealthy")

    try:
        from services.search import init_elasticsearch
        es_ready = await init_elasticsearch()
        if es_ready:
            logger.info("Elasticsearch initialized")
            mark_runtime("elasticsearch", "healthy")
        else:
            logger.warning("Elasticsearch not available at startup")
            mark_runtime("elasticsearch", "unhealthy")
    except Exception as exc:
        logger.warning(f"Elasticsearch init skipped: {exc}")
        mark_runtime("elasticsearch", "unhealthy")

    mark_runtime("celery_monitor", "scheduled")

    yield

    logger.info("Shutting down Social Agent Platform...")
    mark_runtime("app", "stopped")


app = FastAPI(
    title="Social Agent Platform",
    description="AI-powered social media management for the Moroccan market",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

app.mount("/media", StaticFiles(directory="media"), name="media"),

app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:80", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    response.headers["X-Process-Time"] = str(round(time.time() - start, 4))
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.opt(exception=exc).error(
        "Unhandled exception while processing {} {}",
        request.method,
        request.url.path,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error", "type": type(exc).__name__},
    )


app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(accounts.router, prefix="/api/accounts", tags=["Social Accounts"])
app.include_router(posts.router, prefix="/api/posts", tags=["Posts"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["Analytics"])
app.include_router(hashtags.router, prefix="/api/hashtags", tags=["Hashtags"])
app.include_router(comments.router, prefix="/api/comments", tags=["Comments"])
app.include_router(dm.router, prefix="/api/dm", tags=["Direct Messages"])
app.include_router(alerts.router, prefix="/api/alerts", tags=["Alerts"])
app.include_router(calendar.router, prefix="/api/calendar", tags=["Calendar"])
app.include_router(content.router, prefix="/api/content", tags=["Content Generation"])
app.include_router(monitoring.router, prefix="/api/monitoring", tags=["Monitoring"])
app.include_router(profile.router, prefix="/api/profile", tags=["Profile"])
app.include_router(facebook_oauth.router, prefix="/api/auth", tags=["Facebook OAuth"])
app.include_router(instagram_oauth.router, prefix="/api/auth", tags=["Instagram OAuth"])
app.include_router(linkedIn_oauth.router, prefix="/api/auth", tags=["LinkedIn OAuth"])
app.include_router(twitter_oauth.router, prefix="/api/auth", tags=["Twitter OAuth"])
app.include_router(tiktok_oauth.router, prefix="/api/auth", tags=["TikTok OAuth"])
app.include_router(threads_oauth.router, prefix="/api/auth", tags=["Threads OAuth"])
app.include_router(threads_oauth.public_router, tags=["Threads OAuth"])
app.include_router(youtube_oauth.router, prefix="/api/auth", tags=["YouTube OAuth"])
app.include_router(youtube_oauth.public_router, tags=["YouTube OAuth"])
app.include_router(nlp_routes.router, prefix="/api/nlp", tags=["NLP & ML"])
app.include_router(meta_webhooks.router, prefix="/api/webhooks", tags=["Meta Webhooks"])


@app.get("/api/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
        "version": "1.0.0",
        "timestamp": time.time(),
        "environment": settings.environment,
    }

@app.get("/api/ready", tags=["Health"])
async def readiness_check():
    """Shows whether AI models have finished loading. Poll this after startup."""
    from services.ml_engagement import engagement_predictor
    from services.nlp_pipeline import nlp_pipeline
    return {
        "engagement_model_ready": engagement_predictor._is_fitted,
        "nlp_sentiment_loaded": nlp_pipeline._sentiment_model is not None,
        "nlp_toxic_loaded": nlp_pipeline._toxic_model is not None,
        "database": runtime_state.get("database", {}).get("status", "unknown"),
        "hint": "If engagement_model_ready is false, posts will show with a fallback 3% engagement score.",
    }


@app.get("/api/health/detailed", tags=["Health"])
async def detailed_health():
    """Check all service dependencies."""
    checks = {}

    try:
        from core.database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            await session.execute(__import__("sqlalchemy").text("SELECT 1"))
        checks["database"] = "healthy"
    except Exception as exc:
        checks["database"] = f"unhealthy: {exc}"

    try:
        import redis.asyncio as redis
        r = redis.from_url(settings.redis_url)
        await r.ping()
        await r.aclose()
        checks["redis"] = "healthy"
    except Exception as exc:
        checks["redis"] = f"unhealthy: {exc}"

    try:
        from elasticsearch import AsyncElasticsearch
        es = AsyncElasticsearch(settings.elasticsearch_url)
        await es.ping()
        await es.close()
        checks["elasticsearch"] = "healthy"
    except Exception as exc:
        checks["elasticsearch"] = f"unavailable: {exc}"

    overall = "healthy" if all("healthy" in value for value in checks.values()) else "degraded"
    return {"status": overall, "checks": checks, "timestamp": time.time()}


@app.get("/terms", tags=["Legal"])
async def terms_of_service():
    from fastapi.responses import HTMLResponse
    return HTMLResponse("""
    <h1>Terms of Service - Social Agent Command Center</h1>
    <p>This application is a social media management tool for scheduling
    and publishing content across social platforms.</p>
    <p>By using this app, you agree to comply with the terms of service
    of each connected social platform (TikTok, Instagram, Facebook, X, LinkedIn, Threads).</p>
    <p>Last updated: April 2026</p>
    """)


@app.get("/privacy", tags=["Legal"])
async def privacy_policy():
    from fastapi.responses import HTMLResponse
    return HTMLResponse("""
    <h1>Privacy Policy - Social Agent Command Center</h1>
    <p>We collect only the data necessary to connect and manage your social media accounts.</p>
    <p>We do not sell your personal data to third parties.</p>
    <p>OAuth tokens are stored securely and used only to publish content on your behalf.</p>
    <p>Last updated: April 2026</p>
    """)


@app.get("/tiktokmB2C2Eya3GqoR5C7Ab7NMGtQxCKP2Fzv.txt", tags=["TikTok Verification"])
async def tiktok_verification():
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse("tiktok-developers-site-verification=mB2C2Eya3GqoR5C7Ab7NMGtQxCKP2Fzv")


@app.websocket("/ws/alerts")
async def websocket_alerts(websocket: WebSocket):
    from services.alert_dispatcher import ws_manager

    await websocket.accept()

    class _Adapter:
        remote_address = ("ws", 0)

        async def send(self, msg):
            await websocket.send_text(msg)

    adapter = _Adapter()
    ws_manager._connections.add(adapter)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager._connections.discard(adapter)
