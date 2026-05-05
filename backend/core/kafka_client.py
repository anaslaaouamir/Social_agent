"""Kafka producer/consumer clients for social streaming."""
from __future__ import annotations

import json
import logging
import socket
from functools import lru_cache
from typing import Any, Callable, Optional

try:
    from confluent_kafka import Consumer, KafkaError, KafkaException, Producer
    from confluent_kafka.admin import AdminClient, NewTopic
    KAFKA_SDK_AVAILABLE = True
except ModuleNotFoundError:
    Consumer = Producer = AdminClient = NewTopic = None
    KafkaError = KafkaException = None
    KAFKA_SDK_AVAILABLE = False

from core.config import get_settings

settings = get_settings()
logger = logging.getLogger(__name__)


def get_kafka_config() -> dict:
    return {
        "bootstrap.servers": settings.kafka_bootstrap_servers,
        "client.id": "social-agent",
    }


def is_kafka_available(timeout: float = 1.5) -> bool:
    """Best-effort connectivity check before topic creation or consumers."""
    if not KAFKA_SDK_AVAILABLE:
        return False

    bootstrap = settings.kafka_bootstrap_servers.split(",")[0].strip()
    if not bootstrap or ":" not in bootstrap:
        return False
    host, port_str = bootstrap.rsplit(":", 1)
    try:
        with socket.create_connection((host, int(port_str)), timeout=timeout):
            return True
    except OSError:
        return False


class NullKafkaProducer:
    """No-op producer used when Kafka is unavailable."""

    def produce(self, *args: Any, **kwargs: Any):
        logger.debug("Kafka unavailable, skipping produce")

    def poll(self, timeout: float):
        return None

    def flush(self):
        return None


def get_producer() -> Any:
    if not KAFKA_SDK_AVAILABLE:
        logger.warning("confluent_kafka is not installed; Kafka producer is disabled")
        return NullKafkaProducer()
    if not is_kafka_available():
        logger.warning("Kafka broker unavailable; producer is disabled")
        return NullKafkaProducer()
    return Producer(get_kafka_config())


def get_consumer(group_id: str, topics: list[str]) -> Any:
    if not KAFKA_SDK_AVAILABLE:
        raise RuntimeError("confluent_kafka is not installed; Kafka consumer is unavailable")

    config = {
        **get_kafka_config(),
        "group.id": group_id,
        "auto.offset.reset": "latest",
        "enable.auto.commit": True,
        "auto.commit.interval.ms": 1000,
    }
    consumer = Consumer(config)
    consumer.subscribe(topics)
    return consumer


def create_topics_if_not_exist() -> bool:
    """Create required topics when Kafka is reachable."""
    if not KAFKA_SDK_AVAILABLE:
        logger.warning("confluent_kafka is not installed; skipping topic creation")
        return False

    if not is_kafka_available():
        logger.warning("Kafka unavailable, skipping topic creation")
        return False

    admin = AdminClient(get_kafka_config())
    topics = [
        NewTopic(settings.kafka_topic_social_events, num_partitions=4, replication_factor=1),
        NewTopic(settings.kafka_topic_nlp_results, num_partitions=4, replication_factor=1),
        NewTopic(settings.kafka_topic_alerts, num_partitions=2, replication_factor=1),
        NewTopic("social.posts.raw", num_partitions=4, replication_factor=1),
        NewTopic("social.comments.raw", num_partitions=4, replication_factor=1),
        NewTopic("social.dm.raw", num_partitions=2, replication_factor=1),
        NewTopic("social.engagement.metrics", num_partitions=4, replication_factor=1),
    ]

    had_errors = False
    futures = admin.create_topics(topics, request_timeout=10.0)
    for topic, future in futures.items():
        try:
            future.result()
            logger.info(f"Kafka topic created: {topic}")
        except KafkaException as exc:
            if KafkaError is not None and exc.args[0].code() == KafkaError.TOPIC_ALREADY_EXISTS:
                logger.debug(f"Kafka topic already exists: {topic}")
            else:
                had_errors = True
                logger.error(f"Kafka topic creation failed for {topic}: {exc}")
    return not had_errors


class KafkaEventProducer:
    """Kafka event producer."""

    def __init__(self):
        self._producer = get_producer()

    def produce_event(self, topic: str, key: str, value: dict, callback: Optional[Callable] = None):
        def default_callback(err, msg):
            if err:
                logger.error(f"Kafka delivery error: {err}")
            else:
                logger.debug(f"Kafka msg delivered: {msg.topic()}[{msg.partition()}]@{msg.offset()}")

        self._producer.produce(
            topic=topic,
            key=key.encode("utf-8"),
            value=json.dumps(value, default=str).encode("utf-8"),
            callback=callback or default_callback,
        )
        self._producer.poll(0)

    def flush(self):
        self._producer.flush()

    def emit_comment(self, comment_data: dict):
        self.produce_event("social.comments.raw", key=comment_data.get("platform", "unknown"), value=comment_data)

    def emit_post_published(self, post_data: dict):
        self.produce_event(
            "social.posts.raw",
            key=post_data.get("platform", "unknown"),
            value={**post_data, "event_type": "post_published"},
        )

    def emit_dm(self, dm_data: dict):
        self.produce_event("social.dm.raw", key=dm_data.get("platform", "unknown"), value=dm_data)

    def emit_engagement_metric(self, metric_data: dict):
        self.produce_event("social.engagement.metrics", key=metric_data.get("post_id", "unknown"), value=metric_data)

    def emit_alert(self, alert_data: dict):
        self.produce_event(settings.kafka_topic_alerts, key=alert_data.get("severity", "medium"), value=alert_data)


@lru_cache(maxsize=1)
def get_kafka_producer() -> KafkaEventProducer:
    """Create the Kafka producer lazily to avoid reconnect loops at import time."""
    return KafkaEventProducer()
