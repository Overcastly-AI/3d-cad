"""Unit tests for :mod:`py_kit.routes` — the route walker and the sweep.

The negative controls this file exists for, because a gate nobody has watched
fail is a gate nobody knows works:

* :func:`test_a_route_that_loses_its_marker_is_reported_unprotected` — the
  posture direction. Remove the identity dependency from one route and the
  sweep must name that route.
* :func:`test_the_naive_walk_is_refused_by_the_cross_check` — the vacuity
  direction. Hand the sweep the naive ``app.routes`` walk (the one that finds
  three routes on an 89-route app) and it must REFUSE via ``unwalked`` rather
  than report a clean pass over the fraction it saw. The same test asserts
  that the posture check ALONE would have passed, which is the whole reason
  the cross-check has to exist.
* :func:`test_the_raw_route_walk_gets_paths_and_dependencies_wrong` — the
  false-positive direction, and the one that decided this module's design.
  Hand-recursing ``_IncludedRouter.original_router.routes`` gets the right
  COUNT with the wrong PATHS and the wrong DEPENDENCIES; this test pins both
  errors so nobody "simplifies" the module back into them.
"""

from typing import Annotated, Any

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.routing import APIRoute, RouteContext
from py_kit.routes import (
    documented_operations,
    iter_api_routes,
    route_dependencies,
    route_operations,
    sweep_routes,
)

# The sample app deliberately carries a GET+POST route (a multi-method route
# is the case a per-PATH posture claim gets wrong), and FastAPI derives one
# operation id per method from the endpoint name, so it warns about the
# duplicate. Inherent to the fixture, not a defect in it — suppressed here so
# the warning does not become five lines of noise in every CI run.
pytestmark = pytest.mark.filterwarnings("ignore:Duplicate Operation ID:UserWarning")


def marker() -> str:
    """Stands in for ``get_current_user`` / ``get_principal``."""
    return "principal"


Identity = Annotated[str, Depends(marker)]


def wrapping_dependency(who: Identity) -> str:
    """A dependency that DEPENDS on the marker — the nested-arrival shape."""
    return who


def naive_walk(app: FastAPI) -> list[RouteContext]:
    """The walk this module exists to replace (see the module docstring).

    Wrapped in ``RouteContext`` so it is type-compatible with ``routes=``;
    the wrapping changes nothing, because the whole defect is which routes
    are in the list, not how they are spelled.
    """
    return [
        RouteContext(route=route) for route in app.routes if isinstance(route, APIRoute)
    ]


def build_sample_app() -> FastAPI:
    """An app that arrives at its marker by all five routes FastAPI allows."""
    app = FastAPI()

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        return {"status": "ok"}

    # 1. parameter annotation (`user: CurrentUser`)
    by_annotation = APIRouter(prefix="/annotation")

    @by_annotation.get("/one")
    async def one(who: Identity) -> str:  # pyright: ignore[reportUnusedFunction]
        return who

    # 2. router-level dependencies
    by_router = APIRouter(prefix="/router", dependencies=[Depends(marker)])

    @by_router.get("/two")
    async def two() -> str:  # pyright: ignore[reportUnusedFunction]
        return "two"

    # 3. decorator-level dependencies, on a MULTI-METHOD route
    by_decorator = APIRouter(prefix="/decorator")

    @by_decorator.api_route(
        "/three", methods=["GET", "POST"], dependencies=[Depends(marker)]
    )
    async def three() -> str:  # pyright: ignore[reportUnusedFunction]
        return "three"

    # 4. nested inside another dependency, on a router nested in ANOTHER
    #    router — two levels of inclusion, where a one-level walk starts lying.
    by_nesting = APIRouter(prefix="/nested")

    @by_nesting.get("/four")
    async def four(  # pyright: ignore[reportUnusedFunction]
        who: Annotated[str, Depends(wrapping_dependency)],
    ) -> str:
        return who

    by_annotation.include_router(by_nesting)

    # 5. applied at INCLUDE time — the shape whose dependency is recorded on
    #    the inclusion and NOT on the route.
    by_inclusion = APIRouter(prefix="/inclusion")

    @by_inclusion.get("/five")
    async def five() -> str:  # pyright: ignore[reportUnusedFunction]
        return "five"

    # ...and one deliberately open route, the shape every real service has.
    open_router = APIRouter(prefix="/open")

    @open_router.post("/login")
    async def login() -> str:  # pyright: ignore[reportUnusedFunction]
        return "token"

    for router in (by_annotation, by_router, by_decorator, open_router):
        app.include_router(router)
    app.include_router(by_inclusion, dependencies=[Depends(marker)])
    return app


PROBE = ("GET", "/healthz")
OPEN = ("POST", "/open/login")
SAMPLE_OPERATIONS = {
    PROBE,
    OPEN,
    ("GET", "/annotation/one"),
    ("GET", "/router/two"),
    ("GET", "/decorator/three"),
    ("POST", "/decorator/three"),
    ("GET", "/annotation/nested/four"),
    ("GET", "/inclusion/five"),
}


def operations_by_key(app: FastAPI) -> dict[tuple[str, str], RouteContext]:
    return {
        (method, route.path): route
        for route in iter_api_routes(app)
        for method in (route.methods or ())
        if route.path is not None
    }


def test_the_naive_walk_misses_every_included_route() -> None:
    """The trap itself, pinned: this is why :mod:`py_kit.routes` exists.

    Also a live tripwire on the assumption. If FastAPI ever starts flattening
    included routers back into ``app.routes``, this test goes red and tells
    whoever reads it that the module's recursion may have become dead code —
    rather than leaving a stale rationale in a docstring nobody re-derives.
    """
    app = build_sample_app()
    assert route_operations(naive_walk(app)) == {PROBE}, (
        "the naive walk is expected to find ONLY the app's own handlers; if "
        "it now finds the included ones, FastAPI has started flattening again "
        "and this module's rationale needs re-deriving"
    )
    assert route_operations(iter_api_routes(app)) == SAMPLE_OPERATIONS


def test_the_raw_route_walk_gets_paths_and_dependencies_wrong() -> None:
    """NEGATIVE CONTROL 3 — the false-positive direction.

    Reproduces the hand-rolled recursion this module deliberately does not
    use, and pins the two errors that made it unusable. It finds the right
    NUMBER of routes, which is exactly why the mistake survives review.
    """

    def raw_walk(routes: Any) -> Any:
        for route in routes:
            if isinstance(route, APIRoute):
                yield route
            else:
                original = getattr(route, "original_router", None)
                if original is not None:
                    yield from raw_walk(original.routes)

    app = build_sample_app()
    raw = list(raw_walk(app.routes))
    assert len(raw) == len(list(iter_api_routes(app))), (
        "the raw walk finds the right COUNT — a count floor alone would "
        "never have caught either defect below"
    )

    raw_paths = {route.path for route in raw}
    # (a) the nested router keeps only its own prefix.
    assert "/nested/four" in raw_paths
    assert "/annotation/nested/four" not in raw_paths

    # (b) the include-time dependency is invisible, so a protected route
    #     reads as wide open — a gate that cries wolf and then gets muted.
    by_path = {route.path: route for route in raw}
    inclusion = by_path["/inclusion/five"]
    assert marker not in _flatten(inclusion.dependant), (
        "the raw route's dependant is empty for an include-time dependency"
    )
    assert marker in route_dependencies(
        operations_by_key(app)[("GET", "/inclusion/five")]
    )


def _flatten(dependant: Any) -> set[Any]:
    found: set[Any] = set()
    stack = [dependant]
    while stack:
        for sub in stack.pop().dependencies:
            if sub.call is not None:
                found.add(sub.call)
            stack.append(sub)
    return found


def test_a_multi_method_route_is_one_operation_per_method() -> None:
    """A posture claim about a path is a claim about none of its methods."""
    operations = route_operations(iter_api_routes(build_sample_app()))
    assert ("GET", "/decorator/three") in operations
    assert ("POST", "/decorator/three") in operations


def test_dependencies_are_found_however_they_arrive() -> None:
    """All five spellings put the marker somewhere in the dependency tree."""
    routes = operations_by_key(build_sample_app())
    for operation in SAMPLE_OPERATIONS - {PROBE, OPEN}:
        assert marker in route_dependencies(routes[operation]), operation
    assert marker not in route_dependencies(routes[OPEN])


def test_documented_operations_exclude_unschemad_probes() -> None:
    """The second reading is a SUBSET — it cannot prove a walk complete."""
    app = build_sample_app()
    documented = documented_operations(app)
    assert PROBE not in documented
    assert documented == SAMPLE_OPERATIONS - {PROBE}


def test_sweep_partitions_by_the_marker() -> None:
    sweep = sweep_routes(build_sample_app(), markers=(marker,))
    assert sweep.operations == SAMPLE_OPERATIONS
    assert sweep.unwalked == frozenset()
    assert sweep.unprotected == {PROBE, OPEN}
    assert sweep.protected == SAMPLE_OPERATIONS - sweep.unprotected


def test_a_route_that_loses_its_marker_is_reported_unprotected() -> None:
    """NEGATIVE CONTROL 1 — the posture direction.

    An app whose route was shipped without its identity dependency. The sweep
    must name it; a gate that cannot fail here is not protecting anything.
    """
    app = FastAPI()
    router = APIRouter(prefix="/annotation")

    @router.get("/one")
    async def one() -> str:  # pyright: ignore[reportUnusedFunction]
        return "no identity required"

    app.include_router(router)
    sweep = sweep_routes(app, markers=(marker,))
    assert sweep.unprotected == {("GET", "/annotation/one")}
    assert sweep.protected == frozenset()


def test_the_naive_walk_is_refused_by_the_cross_check() -> None:
    """NEGATIVE CONTROL 2 — the vacuity direction.

    Feed the sweep the walk that finds three routes on an 89-route app. The
    posture verdict it produces is CLEAN, which is precisely the failure this
    project has shipped five times; only ``unwalked`` catches it, and it
    catches it by NAME rather than by a number being lower than expected.
    """
    app = build_sample_app()
    sweep = sweep_routes(app, markers=(marker,), routes=naive_walk(app))

    # The part that looks fine. Nothing here is false — it is a verdict about
    # 1 operation of 8, and nothing in it says so.
    assert sweep.operations == {PROBE}
    assert sweep.protected == frozenset()

    # The part that refuses, naming every operation the walk never reached.
    assert sweep.unwalked == SAMPLE_OPERATIONS - {PROBE}
    assert len(sweep.unwalked) == 7


def test_no_markers_means_nothing_is_protected() -> None:
    """The geometry shape: a service with no identity dependency at all.

    Its invariant is the INVERSE of the other two services' — ``protected``
    must be empty — so the sweep has to express "identity-free" as a checkable
    outcome rather than treating an empty marker set as an error.
    """
    sweep = sweep_routes(build_sample_app(), markers=())
    assert sweep.protected == frozenset()
    assert sweep.unprotected == SAMPLE_OPERATIONS
    assert sweep.unwalked == frozenset()


def test_describe_names_the_counts() -> None:
    sweep = sweep_routes(build_sample_app(), markers=(marker,))
    assert sweep.describe("sample") == (
        "sample: 8 operations, 6 authenticated, 2 unauthenticated, 0 unwalked"
    )
