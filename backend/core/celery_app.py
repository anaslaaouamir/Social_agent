"""Celery application factory with task routing and monitoring."""
from pathlib import Path
import importlib.util
import logging
import sys
from celery import Celery
from celery.schedules import crontab

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    # Celery workers on Windows can lose the project root in spawned processes.
    sys.path.insert(0, str(BACKEND_DIR))

from core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


def _available_task_modules() -> list[str]:
    required_modules = [
        "services.scheduler",
        "services.social_publisher",
        "services.comment_monitor",
        "services.analytics",
        "services.report_generator",
    ]
    optional_modules = {
        "services.rag_service": "chromadb",
    }
    available = list(required_modules)

    for module_name, dependency_name in optional_modules.items():
        if importlib.util.find_spec(dependency_name) is None:
            logger.warning(
                "Skipping Celery task module %s because optional dependency %s is not installed",
                module_name,
                dependency_name,
            )
            continue
        available.append(module_name)

    return available

celery_app = Celery(
    "social_agent",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=_available_task_modules(),
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Africa/Casablanca",
    enable_utc=True,
    broker_connection_retry_on_startup=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_routes={
        "services.scheduler.*": {"queue": "scheduling"},
        "services.social_publisher.*": {"queue": "publishing"},
        "services.comment_monitor.*": {"queue": "monitoring"},
        "services.analytics.*": {"queue": "analytics"},
        "services.report_generator.*": {"queue": "reports"},
        "services.nlp_pipeline.*": {"queue": "nlp"},
        "services.rag_service.*": {"queue": "nlp"},
    },
    beat_schedule={
        # Monitor comments every 5 minutes
        "monitor-comments": {
            "task": "services.comment_monitor.monitor_all_accounts",
            "schedule": crontab(minute="*/5"),
        },
        # Check scheduled posts every minute
        "process-scheduled-posts": {
            "task": "services.scheduler.process_due_posts",
            "schedule": crontab(minute="*/1"),
        },
        # Refresh trending hashtags every 2 hours
        "refresh-hashtag-trends": {
            "task": "services.analytics.refresh_hashtag_trends",
            "schedule": crontab(minute=0, hour="*/2"),
        },
        # Generate weekly reports on Monday 8am
        "weekly-report": {
            "task": "services.report_generator.generate_weekly_report",
            "schedule": crontab(minute=0, hour=8, day_of_week=1),
        },
        # Analytics rollup every hour
        "hourly-analytics": {
            "task": "services.analytics.compute_hourly_metrics",
            "schedule": crontab(minute=0),
        },
        "fit-bertopic-daily": {
            "task": "services.nlp_pipeline.fit_topics_from_db",
            "schedule": crontab(minute=0, hour=3),
        },
        'sync-hidden-comments-every-5-mins': {
            'task': 'services.comment_monitor.sync_hidden_comments',
            'schedule': crontab(minute='*/5'),
    },
    },
)
