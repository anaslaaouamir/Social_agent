"""Elasticsearch initialization and search helpers."""
from __future__ import annotations

from loguru import logger


async def init_elasticsearch() -> bool:
    """Initialize ES indices for hashtags and posts when ES is reachable."""
    from elasticsearch import AsyncElasticsearch
    from core.config import get_settings

    settings = get_settings()
    es = AsyncElasticsearch(settings.elasticsearch_url)
    try:
        if not await es.ping():
            logger.warning("Elasticsearch unavailable, skipping index initialization")
            return False

        if not await es.indices.exists(index="hashtags"):
            await es.indices.create(
                index="hashtags",
                body={
                    "mappings": {
                        "properties": {
                            "tag": {"type": "keyword"},
                            "platform": {"type": "keyword"},
                            "trending_score": {"type": "float"},
                            "avg_reach": {"type": "float"},
                            "market": {"type": "keyword"},
                            "updated_at": {"type": "date"},
                        }
                    }
                },
            )
            logger.info("Hashtag ES index created")

        if not await es.indices.exists(index="posts"):
            await es.indices.create(
                index="posts",
                body={
                    "mappings": {
                        "properties": {
                            "caption": {"type": "text", "analyzer": "french"},
                            "hashtags": {"type": "keyword"},
                            "platform": {"type": "keyword"},
                            "published_at": {"type": "date"},
                        }
                    }
                },
            )
            logger.info("Posts ES index created")
        return True
    except Exception as exc:
        logger.warning(f"ES index creation failed: {exc}")
        return False
    finally:
        await es.close()
