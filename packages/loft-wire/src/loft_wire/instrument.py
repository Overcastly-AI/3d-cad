"""The ONE place the wire package lets a server hook into a DTO.

``FeatureError.model_post_init`` counts every feature failure (see the long
comment above that class in :mod:`loft_wire.features` for why the DTO is the
seam and not the ~85 construction sites). The counter itself is a Prometheus
metric, which lives in ``py_kit.metrics`` and drags in ``prometheus_client``,
FastAPI and ``pydantic-settings``. That edge — a wire type importing a service
kit — is precisely the coupling this distribution exists to break, and it was
the only one: every other module under ``loft_wire`` imports nothing but
``pydantic`` and the standard library.

So the arrow is INVERTED rather than cut. ``loft_wire`` publishes an observer
registry and knows nothing about who registers; ``py_kit.metrics`` registers
:func:`py_kit.metrics.record_feature_error` at import time. A process that
imports only ``loft_wire`` (a modelling script, the MCP server) constructs
``FeatureError`` objects through a no-op list; a service, which always imports
``py_kit``, gets the counter.

THE HAZARD THIS CREATES, NAMED SO IT CAN BE GATED: an unregistered observer is
a FLAT LINE, and a flat line reads as "nothing is failing" rather than as
"nothing is counting" — the exact defect class the comment in ``features`` was
written to prevent, moved one step away. Two things hold it down.
``py_kit/__init__.py`` imports ``py_kit.metrics``, so any process that touches
py-kit at all has wired it before it can build a DTO; and
``packages/py-kit/tests/test_metrics.py`` asserts the counter moves when a
``FeatureError`` is CONSTRUCTED, which fails if the registration is ever
dropped. Do not replace that assertion with one that calls
``record_feature_error`` directly: that would test the recorder and stop
testing the wiring, which is the part that can now break.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Final

__all__ = [
    "FeatureErrorObserver",
    "feature_error_observers",
    "notify_feature_error",
    "register_feature_error_observer",
]

#: Called with a ``FeatureError.code`` each time one is constructed.
FeatureErrorObserver = Callable[[str], None]

_OBSERVERS: Final[list[FeatureErrorObserver]] = []


def register_feature_error_observer(observer: FeatureErrorObserver) -> None:
    """Register ``observer``; idempotent, so a re-imported module cannot
    double-count. Registration order is preserved but must not be relied on —
    observers are independent side effects, not a pipeline."""
    if observer not in _OBSERVERS:
        _OBSERVERS.append(observer)


def feature_error_observers() -> tuple[FeatureErrorObserver, ...]:
    """The registered observers, for tests that need to prove the wiring."""
    return tuple(_OBSERVERS)


def notify_feature_error(code: str) -> None:
    """Fan a feature-failure code out to every observer.

    Runs only on a path where something has already failed, so the cost is
    irrelevant; correctness is not. An observer that raises would turn a
    reported feature error into a 500, so they are expected not to — the only
    one in the tree is a Prometheus ``.inc()``.
    """
    for observer in _OBSERVERS:
        observer(code)
