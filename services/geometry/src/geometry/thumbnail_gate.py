"""The thumbnail render gate: background priority, never ahead of modelling.

A register view asks for one thumbnail per row, all at once. Through the
modelling admission gate (:class:`py_kit.admission.AdmissionGate`) that burst
would fill its queue and push its predicted wait past the bound, so another
user's evaluate would be REFUSED with a 503 — a library page breaking somebody's
modelling. So thumbnails never enter that gate:

- a CACHE HIT is an object-store read and is served with no gate at all (the
  ``/meshes`` posture: it consumes none of the resource the gate protects);
- a RENDER passes this gate instead, which never queues. It admits at most
  ``concurrency`` renders (default 1) and only while the modelling gate has
  NOTHING running or queued; otherwise it refuses at once with a 503 and a
  short ``Retry-After``, and the browser asks again later.

So a render can only start on an idle worker, and modelling that arrives while
one runs is admitted by its own gate as if the render were not there (it shares
the core for the render's fraction of a second; it is never queued behind it or
refused because of it).
"""

from typing import Final

from fastapi import Request
from py_kit.admission import AdmissionGate, get_admission_gate
from py_kit.errors import ServiceOverloadedError

#: Where the gate lives on ``app.state``.
THUMBNAIL_GATE_ATTR: Final = "thumbnail_gate"

#: Seconds a refused render is told to wait: a render is ~0.1-1 s and an idle
#: worker is usually seconds away, so a short, fixed interval keeps tiles
#: filling in without hammering a busy worker.
THUMBNAIL_RETRY_AFTER_S: Final = 2


class ThumbnailGate:
    """A no-queue, lower-priority gate for thumbnail renders (one event loop)."""

    def __init__(self, *, concurrency: int = 1) -> None:
        if concurrency < 1:
            raise ValueError("concurrency must be >= 1")
        self._concurrency = concurrency
        self._running = 0

    @property
    def running(self) -> int:
        return self._running

    def _refuse(self, reason: str) -> ServiceOverloadedError:
        return ServiceOverloadedError(
            "Thumbnails render only on an idle geometry worker; this one is busy. "
            "Retry after the interval in Retry-After.",
            retry_after_s=THUMBNAIL_RETRY_AFTER_S,
            details={"reason": reason, "scope": "thumbnail"},
        )

    def acquire(self, modelling: AdmissionGate | None) -> None:
        """Take a render slot, or raise a 503 without waiting. Pair with release."""
        if modelling is not None:
            stats = modelling.stats()
            if stats.running or stats.queued:
                raise self._refuse("modelling_busy")
        if self._running >= self._concurrency:
            raise self._refuse("thumbnail_busy")
        self._running += 1

    def release(self) -> None:
        self._running -= 1


def get_thumbnail_gate(request: Request) -> ThumbnailGate:
    """The app's gate; installed by ``build_app``, created on first use otherwise."""
    gate: ThumbnailGate | None = getattr(request.app.state, THUMBNAIL_GATE_ATTR, None)
    if gate is None:
        gate = ThumbnailGate()
        setattr(request.app.state, THUMBNAIL_GATE_ATTR, gate)
    return gate


def gates(request: Request) -> tuple[ThumbnailGate, AdmissionGate | None]:
    """The thumbnail gate and the modelling gate it defers to."""
    return get_thumbnail_gate(request), get_admission_gate(request)
