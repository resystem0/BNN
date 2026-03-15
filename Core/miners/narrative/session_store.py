"""
miners/narrative/session_store.py
Redis-backed session store for accumulated narrative context.

The NarrativeMiner reads/writes prior narrative from Redis so that context
persists across multi-hop sessions even when requests arrive at different
workers.

Falls back gracefully to an in-memory dict when Redis is unavailable
(development / testing mode).
"""

from __future__ import annotations

from typing import Optional

from config.subnet_config import (
    GRAPH_REDIS_HOST,
    GRAPH_REDIS_PORT,
    SESSION_CACHE_TTL_SECONDS,
    SESSION_REDIS_DB,
)


class SessionStore:
    """
    Async key-value store for session narrative text.

    Args:
        host:  Redis host (default: localhost).
        port:  Redis port (default: 6379).
        db:    Redis database index (default: SESSION_REDIS_DB).
        ttl:   Key TTL in seconds (default: SESSION_CACHE_TTL_SECONDS).
    """

    def __init__(
        self,
        host: str = GRAPH_REDIS_HOST,
        port: int = GRAPH_REDIS_PORT,
        db: int = SESSION_REDIS_DB,
        ttl: int = SESSION_CACHE_TTL_SECONDS,
    ):
        self._ttl = ttl
        self._redis = None
        self._fallback: dict[str, str] = {}

        try:
            import redis.asyncio as aioredis
            self._redis = aioredis.Redis(
                host=host, port=port, db=db,
                decode_responses=True,
                socket_connect_timeout=2,
            )
        except Exception:
            pass  # Redis not available; use in-memory fallback

    async def get(self, session_id: str) -> Optional[str]:
        """Return stored narrative for session_id, or None."""
        if self._redis is not None:
            try:
                return await self._redis.get(f"session:{session_id}")
            except Exception:
                pass
        return self._fallback.get(session_id)

    async def set(self, session_id: str, narrative: str) -> None:
        """Persist narrative for session_id."""
        if self._redis is not None:
            try:
                await self._redis.set(
                    f"session:{session_id}", narrative, ex=self._ttl
                )
                return
            except Exception:
                pass
        self._fallback[session_id] = narrative

    async def delete(self, session_id: str) -> None:
        """Remove session state."""
        if self._redis is not None:
            try:
                await self._redis.delete(f"session:{session_id}")
                return
            except Exception:
                pass
        self._fallback.pop(session_id, None)
