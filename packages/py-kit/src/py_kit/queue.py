"""Thin arq queue client (RESEARCH §4: Redis 7 + arq for geometry jobs).

Enqueue-side only: a settings-driven connection factory and a typed
``enqueue`` helper. Services own their worker/function definitions — no
speculative abstraction here (CLAUDE.md: DRY ≠ premature abstraction).
"""

from typing import Any, Self

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings
from arq.jobs import Job

from py_kit.config import BaseServiceSettings


class QueueConfigurationError(RuntimeError):
    """Raised when the queue is used without ``REDIS_URL`` configured."""


def redis_settings(settings: BaseServiceSettings) -> RedisSettings:
    """Build arq :class:`RedisSettings` from service settings."""
    if settings.redis_url is None:
        raise QueueConfigurationError(
            "REDIS_URL is not set; this service has not opted into the queue."
        )
    return RedisSettings.from_dsn(settings.redis_url)


class QueueClient:
    """Typed enqueue-side wrapper around an arq redis pool."""

    def __init__(self, pool: ArqRedis) -> None:
        self._pool = pool

    @classmethod
    async def connect(cls, settings: BaseServiceSettings) -> Self:
        """Open a redis pool from ``settings.redis_url``."""
        return cls(await create_pool(redis_settings(settings)))

    async def enqueue(
        self,
        function: str,
        *args: Any,
        _job_id: str | None = None,
        _queue_name: str | None = None,
        **kwargs: Any,
    ) -> Job | None:
        """Submit a job. Returns ``None`` iff ``_job_id`` already exists."""
        return await self._pool.enqueue_job(
            function,
            *args,
            _job_id=_job_id,
            _queue_name=_queue_name,
            **kwargs,
        )

    async def close(self) -> None:
        """Release the underlying redis pool."""
        await self._pool.aclose()
