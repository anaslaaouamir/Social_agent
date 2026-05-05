"""Analytics Celery tasks."""
from core.celery_app import celery_app
from loguru import logger


@celery_app.task(name="services.analytics.compute_hourly_metrics")
def compute_hourly_metrics():
    logger.info("Computing hourly analytics metrics...")


@celery_app.task(name="services.analytics.refresh_hashtag_trends")
def refresh_hashtag_trends():
    logger.info("Refreshing hashtag trends...")
