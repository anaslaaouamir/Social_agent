"""Report generator Celery task."""
from core.celery_app import celery_app
from loguru import logger


@celery_app.task(name="services.report_generator.generate_weekly_report")
def generate_weekly_report():
    logger.info("Generating weekly report...")
