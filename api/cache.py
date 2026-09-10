"""Redis cache client and route caching utilities."""
from __future__ import annotations

import functools
import json
import logging
import os
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Callable
import redis

LOGGER = logging.getLogger(__name__)

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

_redis_pool: redis.ConnectionPool | None = None


def get_redis_client() -> redis.Redis | None:
    """Lazily obtain a verified Redis client."""
    global _redis_pool
    try:
        if _redis_pool is None:
            _redis_pool = redis.ConnectionPool(
                host=REDIS_HOST,
                port=REDIS_PORT,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
        client = redis.Redis(connection_pool=_redis_pool)
        client.ping()
        return client
    except Exception as exc:
        LOGGER.error("Redis connection failed to %s:%s: %s", REDIS_HOST, REDIS_PORT, exc)
        return None


def _json_serializer(obj: Any) -> Any:
    """Serialize non-standard types returned by PostgreSQL cursors."""
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    return str(obj)


def cache_endpoint(ttl_seconds: int = 300) -> Callable:
    """Decorator to cache endpoint responses in Redis."""
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            client = get_redis_client()
            if client is None:
                LOGGER.warning("Redis unavailable; bypassing cache for %s.", func.__name__)
                return func(*args, **kwargs)

            # Build deterministic cache key
            serialized_kwargs = json.dumps(kwargs, sort_keys=True, default=_json_serializer)
            cache_key = f"nba_api:{func.__name__}:{serialized_kwargs}"

            try:
                cached_data = client.get(cache_key)
                if cached_data is not None:
                    LOGGER.info("CACHE HIT: %s", cache_key)
                    return json.loads(cached_data)
            except Exception as err:
                LOGGER.error("Redis read error on key %s: %s", cache_key, err)

            LOGGER.info("CACHE MISS: %s -> executing database query", cache_key)
            result = func(*args, **kwargs)

            try:
                serialized_payload = json.dumps(result, default=_json_serializer)
                client.setex(name=cache_key, time=ttl_seconds, value=serialized_payload)
                LOGGER.info("CACHE SAVED: %s (TTL: %ds)", cache_key, ttl_seconds)
            except Exception as err:
                LOGGER.error("Redis write error on key %s: %s", cache_key, err)

            return result

        return wrapper

    return decorator