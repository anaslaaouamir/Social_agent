"""Scheduler service - Celery tasks for post publishing."""
from __future__ import annotations
from pathlib import Path
import sys
import time
from loguru import logger

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.celery_app import celery_app


def _load_scheduler_models():
    try:
        from models.domain import Post, SocialAccount, PostStatus
    except ModuleNotFoundError:
        from backend.models.domain import Post, SocialAccount, PostStatus
    return Post, SocialAccount, PostStatus


def _load_social_publisher():
    try:
        from services.social_publisher import SocialPublisherService
    except ModuleNotFoundError:
        from backend.services.social_publisher import SocialPublisherService
    return SocialPublisherService


@celery_app.task(name="services.scheduler.publish_post_task", bind=True, max_retries=3)
def publish_post_task(self, post_id: str):
    """Celery task: publish a post to its social platform."""
    import asyncio
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from core.config import get_settings
    settings = get_settings()

    try:
        # Use sync DB for Celery
        from sqlalchemy import create_engine, select
        from sqlalchemy.orm import Session
        import uuid
        Post, SocialAccount, PostStatus = _load_scheduler_models()

        engine = create_engine(settings.sync_database_url)
        with Session(engine) as session:
            post = session.get(Post, uuid.UUID(post_id))
            if not post:
                logger.error(f"Post {post_id} not found")
                return

            account = session.get(SocialAccount, post.account_id)
            if not account:
                logger.error(f"Account not found for post {post_id}")
                return

            # Run async publisher in sync context
            async def _publish():
                SocialPublisherService = _load_social_publisher()
                publisher = SocialPublisherService(
                    instagram_token=account.access_token if account.platform.value == "instagram" else "",
                    instagram_account_id=account.account_id if account.platform.value == "instagram" else "",
                    tiktok_token=account.access_token if account.platform.value == "tiktok" else "",
                    linkedin_token=account.access_token if account.platform.value == "linkedin" else "",
                    linkedin_member_id=account.account_id if account.platform.value == "linkedin" else "",
                    facebook_token=account.access_token if account.platform.value == "facebook" else "",
                    facebook_page_id=account.account_id if account.platform.value == "facebook" else "",
                    twitter_token=account.access_token if account.platform.value == "twitter" else "",
                    twitter_user_id=account.account_id if account.platform.value == "twitter" else "",
                    threads_token=account.access_token if account.platform.value == "threads" else "",
                    threads_user_id=account.account_id if account.platform.value == "threads" else "",
                    youtube_token=account.access_token if account.platform.value == "youtube" else "",
                    youtube_channel_id=account.account_id if account.platform.value == "youtube" else "",
                )
                return await publisher.publish_to_platform(
                    platform=account.platform.value,
                    caption=post.caption or "",
                    media_urls=post.media_urls,
                    content_type=post.content_type.value,
                    hashtags=post.hashtags,
                    source_post_id=str(post.id),
                )

            result = asyncio.run(_publish())

            if result.status.value == "success":
                post.status = PostStatus.PUBLISHED
                post.platform_post_id = result.platform_post_id
                post.published_at = result.published_at or time.time()
                logger.info(f"Post {post_id} published successfully: {result.platform_post_id}")
            else:
                post.status = PostStatus.FAILED
                logger.error(f"Post {post_id} publish failed: {result.error_message}")

            session.commit()

    except Exception as exc:
        logger.error(f"Publish task failed: {exc}")
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@celery_app.task(name="services.scheduler.process_due_posts")
def process_due_posts():
    """Check for posts due for publishing and enqueue them."""
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session
    from core.config import get_settings
    Post, PostStatus, _ = None, None, None
    Post, _, PostStatus = _load_scheduler_models()
    settings = get_settings()

    engine = create_engine(settings.sync_database_url)
    now = time.time()
    window = now + 60  # Posts due within next 60 seconds

    with Session(engine) as session:
        due_posts = session.execute(
            select(Post).where(
                Post.status == PostStatus.SCHEDULED,
                Post.scheduled_at <= window,
                Post.scheduled_at >= now - 300,  # not more than 5 min late
            )
        ).scalars().all()

        for post in due_posts:
            post.status = PostStatus.PUBLISHING
            session.commit()
            publish_post_task.delay(str(post.id))
            logger.info(f"Enqueued post {post.id} for publishing")
