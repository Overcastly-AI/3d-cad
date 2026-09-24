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
one accepted intent is spent: one prefix, under ONE budget, cancellable.

ONE LINEAGE, WHATEVER THE TICKET NAMES. A warm request still lists
``lineages`` (``evaluate``, ``provenance``), from when a face pick
(``record_history=True``) had a cache lineage of its own: the plain prefix
recorded no per-face provenance, so the pick after every commit rebuilt the
whole tree unless the warm had built that second lineage too. Since PERF-REAL-3
every evaluation records, both names address the SAME key, and warming it once
serves the commit and the pick after it. Warming it "twice" would only put the
first result back — so the lineages are collapsed here, and a ticket naming
none warms nothing, exactly as before.
"""

from collections.abc import Callable

from loft_wire.features import WarmTreeRequest

from geometry.features.evaluate import warm_rebuild_cache
from geometry.rebuild_cache import WarmScheduler, live_work

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
    OCCT call.

    The warm is handed the process's live-work gate, which is what makes the
    prefetch safe to fire early: with one effective core per worker (CONC-5),
    speculation that keeps running through a real rebuild takes half of it — the
    measured cost was a commit going 2 589 -> 4 742 ms. With the gate the warm
    banks its prefix and steps aside instead, so the worst case is "the guess
    achieved nothing" rather than "the user waited longer".

    Nothing is returned to anybody: the count each warm cached is deliberately
    dropped on the floor, because there is no caller left to tell. What the warm
    leaves behind is reachable only through the ordinary content-addressed key.
    """

    def run(should_stop: Callable[[], bool]) -> None:
        if not request.lineages or should_stop():
            return
        warm_rebuild_cache(
            request.tree,
            prefix_length=request.prefix_length,
            cancelled=should_stop,
            yield_to=live_work(),
        )

    return run
