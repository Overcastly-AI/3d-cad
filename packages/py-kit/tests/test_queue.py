"""py_kit.queue — settings-driven redis factory + typed enqueue wrapper."""

import asyncio
from typing import cast
from unittest.mock import AsyncMock

import pytest
from arq.connections import ArqRedis
from py_kit.config import BaseServiceSettings
from py_kit.queue import QueueClient, QueueConfigurationError, redis_settings


def test_redis_settings_requires_url() -> None:
    with pytest.raises(QueueConfigurationError):
        redis_settings(BaseServiceSettings(redis_url=None))


def test_redis_settings_parses_dsn() -> None:
    parsed = redis_settings(BaseServiceSettings(redis_url="redis://queue-host:6380/2"))
    assert parsed.host == "queue-host"
    assert parsed.port == 6380
    assert parsed.database == 2


def test_enqueue_delegates_to_pool() -> None:
    pool = AsyncMock(spec=ArqRedis)
    client = QueueClient(cast(ArqRedis, pool))

    job = asyncio.run(
        client.enqueue("tessellate", "doc-1", _job_id="job-1", quality="fine")
    )

    pool.enqueue_job.assert_awaited_once_with(
        "tessellate", "doc-1", _job_id="job-1", _queue_name=None, quality="fine"
    )
    assert job is pool.enqueue_job.return_value


def test_close_releases_pool() -> None:
    pool = AsyncMock(spec=ArqRedis)
    client = QueueClient(cast(ArqRedis, pool))
    asyncio.run(client.close())
    pool.aclose.assert_awaited_once()
