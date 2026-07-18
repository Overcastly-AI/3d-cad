"""Geometry arq worker — task function + typed enqueue helper.

Runtime queue verification (a live redis + arq worker) is deferred until the
dev stack runs redis; the task function is unit-tested directly per the
first-light scope.
"""

import asyncio
from typing import Any, cast

import pytest
from arq.connections import ArqRedis
from geometry.schemas import TessellateRequest, TessellationMetadata
from geometry.worker import (
    TESSELLATE_TASK,
    WorkerSettings,
    enqueue_tessellate,
    tessellate_shape,
)
from py_kit import QueueClient

#: Documented golden tolerance — see tests/test_kernel.py.
GOLDEN_TOL = 1e-7

PAYLOAD: dict[str, Any] = {
    "shape": "box",
    "params": {"x": 10.0, "y": 20.0, "z": 30.0},
    "linear_deflection": 0.1,
}


def test_task_returns_metadata_dump() -> None:
    result = asyncio.run(tessellate_shape({}, PAYLOAD))

    metadata = TessellationMetadata.model_validate(result)
    assert metadata.properties.volume == pytest.approx(6000.0, abs=GOLDEN_TOL)
    assert metadata.properties.topology.faces == 6
    assert metadata.mesh.triangles == 12


def test_task_rejects_invalid_payload() -> None:
    bad = {**PAYLOAD, "params": {"x": -1.0, "y": 1.0, "z": 1.0}}
    with pytest.raises(ValueError):
        asyncio.run(tessellate_shape({}, bad))


class _RecordingPool:
    """Duck-typed ArqRedis capturing enqueue_job calls."""

    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []

    async def enqueue_job(self, function: str, *args: Any, **kwargs: Any) -> None:
        self.calls.append((function, args, kwargs))
        return None


def test_enqueue_helper_submits_the_registered_task() -> None:
    pool = _RecordingPool()
    queue = QueueClient(cast(ArqRedis, pool))
    request = TessellateRequest.model_validate(PAYLOAD)

    asyncio.run(enqueue_tessellate(queue, request, job_id="job-1"))

    (function, args, kwargs) = pool.calls[0]
    assert function == TESSELLATE_TASK
    assert args == (PAYLOAD,)
    assert kwargs["_job_id"] == "job-1"


def test_worker_settings_register_the_task() -> None:
    names = [function.name for function in WorkerSettings.functions]
    assert names == [TESSELLATE_TASK]


def test_worker_redis_settings_none_without_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Importing/instantiating never requires REDIS_URL (resolve returns None)."""
    from geometry.worker import redis_settings_from_env

    monkeypatch.delenv("REDIS_URL", raising=False)
    assert redis_settings_from_env() is None
