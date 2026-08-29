"""Route introspection — the one place that knows FastAPI's route topology.

WHY THIS EXISTS, and why it is not four lines of ``for route in app.routes``.

**FastAPI >= 0.139 does not flatten included routers into ``app.routes``.**
An ``app.include_router(r)`` appends a single ``fastapi.routing._IncludedRouter``
wrapper and the real routes stay on ``r``. So the obvious walk finds the app's
own handlers and nothing else. Measured on this repo's gateway at the commit
that added this module::

    naive  [r for r in app.routes if isinstance(r, APIRoute)]  ->   3
    iter_api_routes(app)                                       ->  89

Three is not a small error, it is the *shape of a pass*: a checker that walks
naively and then asserts "every route it found is authenticated" is checking
``/healthz``, ``/readyz`` and ``/metrics`` and calling the other 86 clean.
``all([])`` and ``all([three probes])`` are both ``True``, and this repo has
shipped that failure five times in other gates. An engineering audit
reproduced it *live* while auditing for exactly this problem — its first sweep
reported the gateway as "3 routes, nothing to check".

WHY IT DELEGATES TO ``fastapi.routing.iter_route_contexts``

Recursing ``_IncludedRouter.original_router.routes`` by hand gets the COUNT
right and two things that matter more WRONG, both measured before this module
was written:

* **the path** — a router included into another router keeps its own prefix
  only. ``inner`` at ``/inner`` included into ``outer`` at ``/outer`` reports
  ``/inner/leaf`` where the app actually serves ``/outer/inner/leaf``.
* **the dependencies** — ``app.include_router(r, dependencies=[Depends(auth)])``
  records the dependency on the *inclusion*, not on the route, so the original
  route's ``dependant`` is EMPTY. A posture check reading it would report a
  correctly-authenticated router as wide open.

That second one is the dangerous direction. A gate that cries wolf gets muted,
and a muted gate protects nothing — so being wrong about a route that IS
protected is worse here than the extra code needed to be right.
``iter_route_contexts`` is the flattener FastAPI's own OpenAPI generator uses
(``fastapi.openapi.utils.get_fields_from_routes``); it composes prefixes and
merges inclusion-level dependencies, tags and ``include_in_schema`` into an
effective view of each route. Delegating to it means every arrival shape
FastAPI supports is handled by FastAPI, now and after the next refactor.

It is imported at module scope on purpose: if a future version removes it,
this module fails to import and every caller goes red at once. The failure
mode to avoid is the quiet one, where a walker degrades to a partial answer
and the suite stays green over a fraction of the app.

WHAT THE CALLER GETS

:func:`sweep_routes` returns a :class:`RouteSweep` carrying the posture
(:attr:`~RouteSweep.protected` / :attr:`~RouteSweep.unprotected`) and, beside
it, :attr:`~RouteSweep.unwalked` — the operations the app's own OpenAPI schema
describes that the walk did not reach. Be precise about what that buys: in
production both readings now come from ``iter_route_contexts``, so it is a
consistency check, not an independent oracle. Its real work is done in two
places — it lets a test hand the sweep a KNOWN-BAD walk and prove the sweep
REFUSES it (see ``routes=`` below), and when a walk does shrink it reports
which operations went missing by name instead of a number that is merely
lower than someone expected.

**Callers must therefore also assert a COUNT FLOOR.** Both readings shrink
together if a whole router stops being included, and nothing here notices
that; only a floor does.

Dependency detection is by **object identity**, never by name. Pass the
identity dependency itself (``markers=(get_current_user,)``) rather than a
string: renaming the function then breaks the caller's import loudly, instead
of silently matching nothing and reporting every route unprotected — or, far
worse, matching some unrelated function that happens to share a name.
"""

from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute, RouteContext, iter_route_contexts

#: An HTTP operation: ``("POST", "/api/v1/parts")``. Routes are keyed per
#: METHOD, not per path — one route can serve several methods, and a posture
#: claim about "the path" would be a claim about none of them.
Operation = tuple[str, str]

#: The lowercase keys ``paths.<path>.<key>`` that denote an operation in an
#: OpenAPI path item. Everything else there (``parameters``, ``summary``,
#: ``$ref``, ``servers``) is metadata about the path, not an operation.
_OPENAPI_METHODS = frozenset(
    {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
)


def iter_api_routes(app: FastAPI) -> Iterator[RouteContext]:
    """Every API route of *app* in its EFFECTIVE form, included routers too.

    Yields ``fastapi.routing.RouteContext`` objects, not ``APIRoute`` objects:
    a context proxies ``path``, ``methods``, ``dependant`` and
    ``include_in_schema`` to the route as the app actually serves it, with
    prefixes composed and inclusion-level dependencies merged in (see the
    module docstring for what reading the raw ``APIRoute`` gets wrong).

    Non-API routes are excluded — the Starlette routes behind ``/openapi.json``,
    ``/docs`` and ``/redoc`` carry no dependency tree and are not part of any
    service's API surface. They are identified by their ORIGINAL route's type,
    which is the one thing about a context that is never rewritten.
    """
    for context in iter_route_contexts(app.routes):
        if isinstance(context.original_route, APIRoute):
            yield context


def route_operations(routes: Iterable[RouteContext]) -> frozenset[Operation]:
    """The ``(METHOD, path)`` set *routes* serves."""
    return frozenset(
        (method, route.path)
        for route in routes
        for method in (route.methods or ())
        if route.path is not None
    )


def documented_operations(app: FastAPI) -> frozenset[Operation]:
    """The ``(METHOD, path)`` set *app*'s own OpenAPI schema describes.

    Routes registered with ``include_in_schema=False`` (py-kit's ``/healthz``,
    ``/readyz`` and ``/metrics`` probes) are absent here by construction, so
    this set is a SUBSET of a correct walk — it can prove a walk incomplete,
    never that one is complete.
    """
    schema: dict[str, Any] = app.openapi()
    paths: dict[str, dict[str, Any]] = schema.get("paths", {})
    return frozenset(
        (method.upper(), path)
        for path, item in paths.items()
        for method in item
        if method in _OPENAPI_METHODS
    )


def route_dependencies(route: RouteContext) -> frozenset[Callable[..., Any]]:
    """Every dependency callable in *route*'s dependency tree, flattened.

    Flattened because a route's identity dependency is not always a direct
    child. It can arrive as a parameter annotation (``user: CurrentUser``), as
    ``APIRouter(dependencies=[...])``, as ``@router.post(...,
    dependencies=[...])``, as ``include_router(..., dependencies=[...])``, or
    nested inside another dependency. All five land somewhere in this tree and
    nowhere predictable in it, so a check that only read
    ``dependant.dependencies`` would be a check that happens to work on
    today's spelling of today's routes.
    """
    dependant: Dependant | None = getattr(route, "dependant", None)
    if dependant is None:
        return frozenset()
    found: set[Callable[..., Any]] = set()
    stack: list[Dependant] = [dependant]
    while stack:
        for sub in stack.pop().dependencies:
            if sub.call is not None:
                found.add(sub.call)
            stack.append(sub)
    return frozenset(found)


@dataclass(frozen=True)
class RouteSweep:
    """What a walk of one app's routes found. See :func:`sweep_routes`."""

    #: Every operation the walk reached.
    operations: frozenset[Operation]
    #: Operations whose dependency tree contains at least one marker.
    protected: frozenset[Operation]
    #: Operations whose dependency tree contains none. Every one of these is
    #: reachable without presenting an identity, and must be on an exempt
    #: list with a stated reason — or be a defect.
    unprotected: frozenset[Operation]
    #: Documented operations the walk did NOT reach. **Must be empty.** A
    #: non-empty set means the walk is broken and every other field here is
    #: describing a fraction of the app; see the module docstring.
    unwalked: frozenset[Operation]

    def describe(self, service: str) -> str:
        """One line for a CI log: the counts a human needs to see."""
        return (
            f"{service}: {len(self.operations)} operations, "
            f"{len(self.protected)} authenticated, "
            f"{len(self.unprotected)} unauthenticated, "
            f"{len(self.unwalked)} unwalked"
        )


def sweep_routes(
    app: FastAPI,
    *,
    markers: Iterable[Callable[..., Any]],
    routes: Iterable[RouteContext] | None = None,
) -> RouteSweep:
    """Partition *app*'s operations by whether they require an identity.

    *markers* are the dependency callables that constitute authentication for
    this service, compared by identity (see the module docstring). A service
    with no identity dependency at all — the geometry kernel, which never sees
    a user — passes an empty ``markers`` and asserts that
    :attr:`RouteSweep.protected` is empty: for that service the invariant is
    the INVERSE, and asserting "everything is authenticated" there would be
    asserting the wrong thing loudly.

    *routes* overrides the walk. Production callers leave it ``None``; it
    exists so a test can feed a KNOWN-BAD walk (e.g. the naive ``app.routes``
    filter) and prove :attr:`RouteSweep.unwalked` refuses it rather than
    reporting a clean 3-of-3.
    """
    walked = list(iter_api_routes(app)) if routes is None else list(routes)
    marker_set = frozenset(markers)
    protected: set[Operation] = set()
    unprotected: set[Operation] = set()
    for route in walked:
        if route.path is None:
            continue
        bucket = protected if route_dependencies(route) & marker_set else unprotected
        for method in route.methods or ():
            bucket.add((method, route.path))
    operations = route_operations(walked)
    return RouteSweep(
        operations=operations,
        protected=frozenset(protected),
        unprotected=frozenset(unprotected),
        unwalked=documented_operations(app) - operations,
    )
