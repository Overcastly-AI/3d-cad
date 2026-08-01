"""The prefetch wiring: a warm request → work on the worker's one warm thread.

Three modules meet here and each keeps its own concern:
:mod:`geometry.rebuild_cache` owns the cache and the bounded, cancellable
:class:`~geometry.rebuild_cache.WarmScheduler` (and knows nothing about feature
trees); :func:`geometry.features.evaluate.warm_rebuild_cache` owns what a warm
IS (dispatch a prefix, store a checkpoint, publish nothing); this module is the
short seam between them plus the per-worker singleton, so :mod:`geometry.api`
stays the thin HTTP shell it says it is.

WHAT IS AND IS NOT DECIDED HERE. The two triggers (an open feature editor, a
dragged travel stop) are decided in the browser, because intent lives there and
nowhere else — a service cannot tell "the user opened the editor for feature 100"
from "something asked about feature 100". What this module decides is only how
one accepted intent is spent: lineages in the order the user will consume them,
under ONE budget, all of it cancellable.

WHY LINEAGES ARE ORDERED AND SHARE A BUDGET. After an edit the user commits (a
plain rebuild) and then, overwhelmingly, clicks a face (a provenance rebuild —
``record_history=True``, a separate cache lineage because the plain prefix
retains no intermediate bodies). Both are worth warming, but they are not worth
the same: the commit is what the user is waiting on with their hand on the mouse,
and the pick comes at least a second later. So ``evaluate`` runs first and
``provenance`` gets what is left of the budget — a warm that runs out of time has
always done the more valuable half.
"""

from collections.abc import Callable

from py_kit.schemas.features import WarmTreeRequest

from geometry.features.evaluate import warm_rebuild_cache
from geometry.rebuild_cache import WarmScheduler

#: The per-worker speculation slot (process-global like the caches themselves).
#: ONE, so prefetch across every client of this worker can never cost more than
#: one core; see :class:`~geometry.rebuild_cache.WarmScheduler`.
_WARM_SCHEDULER = WarmScheduler()


def warm_scheduler() -> WarmScheduler:
    """The process's warm scheduler (the API route and the tests share it)."""
    return _WARM_SCHEDULER


def warm_work(request: WarmTreeRequest) -> Callable[[Callable[[], bool]], None]:
    """The work one accepted warm ticket represents.

    Returns a callable the scheduler runs on its thread, handed the ``should_stop``
    predicate that folds in both the budget and supersede/cancel. The predicate is
    threaded straight through to ``warm_rebuild_cache``, which polls it BETWEEN
    features — the honest granularity, since one feature is one uninterruptible
    OCCT call — and re-checked between lineages so a cancelled ticket cannot start
    the second one.

    Nothing is returned to anybody: the count each warm cached is deliberately
    dropped on the floor, because there is no caller left to tell. What the warm
    leaves behind is reachable only through the ordinary content-addressed key.
    """

    def run(should_stop: Callable[[], bool]) -> None:
        for lineage in dict.fromkeys(request.lineages):
            if should_stop():
                return
            warm_rebuild_cache(
                request.tree,
                prefix_length=request.prefix_length,
                record_history=lineage == "provenance",
                cancelled=should_stop,
            )

    return run
