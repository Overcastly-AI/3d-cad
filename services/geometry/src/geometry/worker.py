"""Geometry arq worker — queue path to the same kernel core as the REST API.

Design (RESEARCH §4): callers enqueue jobs via :func:`enqueue_tessellate`;
the worker (``arq geometry.worker.WorkerSettings``) evaluates them with
:func:`geometry.kernel.evaluate_tessellation` and returns metadata. Meshes
never travel through redis — the GLB upload to object storage (MinIO/S3)
lands with the storage backlog item, at which point the task result gains an
artifact reference.

Payloads cross the queue as plain dicts (arq-serializable) and are
re-validated into DTOs on the worker side.
"""

from typing import Any, ClassVar

from arq.connections import RedisSettings
from arq.jobs import Job
from arq.worker import Function, func
from py_kit import QueueClient
from py_kit import redis_settings as build_redis_settings

from geometry.kernel import evaluate_tessellation
from geometry.schemas import TessellateRequest

#: Queue name of the tessellation task (single source for both sides).
TESSELLATE_TASK = "tessellate_shape"


async def tessellate_shape(
    ctx: dict[str, Any], payload: dict[str, Any]
) -> dict[str, Any]:
    """arq task: validate the payload, run the kernel, return metadata.

    Returns ``TessellationMetadata.model_dump()`` — plain JSON-safe data,
    never kernel types. The GLB artifact is discarded until the object
    storage item lands (see module docstring).
    """
    request = TessellateRequest.model_validate(payload)
    _glb, metadata = evaluate_tessellation(request)
    return metadata.model_dump()


async def enqueue_tessellate(
    queue: QueueClient,
    request: TessellateRequest,
    *,
    job_id: str | None = None,
) -> Job | None:
    """Typed enqueue helper — the only sanctioned way to submit the task."""
    return await queue.enqueue(TESSELLATE_TASK, request.model_dump(), _job_id=job_id)


def redis_settings_from_env() -> RedisSettings | None:
    """Resolve arq redis settings from ``REDIS_URL`` without failing imports.

    ``None`` (env unset) only matters when actually launching the worker;
    importing this module must stay side-effect free.
    """
    from geometry.main import GeometrySettings

    settings = GeometrySettings()
    if settings.redis_url is None:
        return None
    return build_redis_settings(settings)


class WorkerSettings:
    """arq worker settings: ``arq geometry.worker.WorkerSettings``.

    Runtime queue verification is deferred until redis is runnable in the
    dev stack; the task function is unit-tested directly.
    """

    functions: ClassVar[list[Function]] = [func(tessellate_shape, name=TESSELLATE_TASK)]
    redis_settings: ClassVar[RedisSettings | None] = redis_settings_from_env()
